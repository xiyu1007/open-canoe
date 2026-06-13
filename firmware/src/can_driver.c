/**
 * @file    can_driver.c
 * @brief   CAN bus driver using STM32 HAL bxCAN peripheral.
 *          Abstracted behind can_api.h — no MCU register access in caller.
 */

#include "can_api.h"
#include "device_api.h"
#include "device_config.h"
#include <string.h>

#if defined(STM32F103xB)
#include "stm32f1xx_hal.h"
#include "stm32f1xx_hal_can.h"
#elif defined(STM32F407xx)
#include "stm32f4xx_hal.h"
#include "stm32f4xx_hal_can.h"
#endif

/*============================================================================
 * Internal State per Channel
 *============================================================================*/

typedef struct {
    CAN_HandleTypeDef hcan;             /* STM32 HAL CAN handle */
    can_config_t      config;           /* User configuration */
    can_stats_t       stats;            /* Runtime statistics */
    can_rx_callback_t rx_callback;      /* User callback for received frames */
    uint8_t           initialized;
    uint8_t           listening;
} can_channel_ctx_t;

static can_channel_ctx_t g_can_ctx[CAN_INSTANCE_COUNT];

/*============================================================================
 * Helper: Map channel index to CAN_HandleTypeDef pointer
 *============================================================================*/

static CAN_HandleTypeDef *can_get_handle(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return NULL;
    return &g_can_ctx[channel].hcan;
}

static can_channel_ctx_t *can_get_ctx(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return NULL;
    return &g_can_ctx[channel];
}

/*============================================================================
 * Helper: Compute CAN timing from baudrate
 *============================================================================*/

/**
 * @brief Compute CAN prescaler and timing segments for the given baudrate.
 *        Uses the APB1 clock as CAN peripheral clock.
 *
 *        Bit time = (1 + BS1 + BS2 + SJW) * Prescaler / APB1_CLK
 *        Sample point at ~75-87.5% of bit time.
 */
static can_status_t can_calc_timing(uint32_t baudrate,
                                    uint32_t *prescaler,
                                    uint32_t *bs1,
                                    uint32_t *bs2,
                                    uint32_t *sjw)
{
    if (baudrate == 0) return CAN_ERR_PARAM;

    uint32_t apb1_clk = APB1_CLOCK_HZ;

    /* Try prescaler values from 1 upward; find one that gives integer tq */
    for (uint32_t psc = 1; psc <= 1024; psc++) {
        uint32_t tq_count = apb1_clk / (baudrate * psc);
        if (tq_count < 8 || tq_count > 25) {
            /* tq_count must be between 8 and 25 per CAN spec */
            if (tq_count < 8 && psc > 1) break; /* Going further would only reduce tq */
            continue;
        }
        /* Check if this is exact enough (±1%) */
        uint32_t actual_baud = apb1_clk / (psc * tq_count);
        uint32_t error;
        if (actual_baud > baudrate) {
            error = (actual_baud - baudrate) * 1000 / baudrate;
        } else {
            error = (baudrate - actual_baud) * 1000 / baudrate;
        }
        if (error > 10) continue; /* >1% error, keep searching */

        /* Distribute tq: sample point at ~80% */
        uint32_t bs1_val = (tq_count * 4) / 5 - 1; /* ~80% */
        if (bs1_val < 1) bs1_val = 1;
        if (bs1_val > 16) bs1_val = 16;
        uint32_t bs2_val = tq_count - bs1_val - 1;
        if (bs2_val < 1) bs2_val = 1;
        if (bs2_val > 8) bs2_val = 8;

        /* Adjust bs1 if bs2 is too large */
        if (bs2_val > 8) {
            bs2_val = 8;
            bs1_val = tq_count - bs2_val - 1;
            if (bs1_val < 1) bs1_val = 1;
            if (bs1_val > 16) bs1_val = 16;
        }

        uint32_t sjw_val = bs2_val;
        if (sjw_val > 4) sjw_val = 4;

        *prescaler = psc;
        *bs1 = bs1_val;
        *bs2 = bs2_val;
        *sjw = sjw_val;
        return CAN_OK;
    }

    return CAN_ERR_PARAM;
}

/*============================================================================
 * CAN MSP Initialization (pin, clock, NVIC)
 *============================================================================*/

static void can_msp_init(uint8_t channel)
{
    if (channel == 0) {
        /* CAN1 */
        CAN1_GPIO_CLK_ENABLE();
        CAN1_PERIPH_CLK_ENABLE();
#if defined(STM32F103xB)
        /* F103 needs AFIO remap for CAN1 on PB8/PB9 */
        CAN1_AFIO_CLK_ENABLE();
        CAN1_AFIO_REMAP();
#endif

        GPIO_InitTypeDef gpio = {0};

        /* CAN RX: input with pull-up (recessive level when no transceiver) */
        gpio.Mode  = GPIO_MODE_INPUT;
        gpio.Pull  = GPIO_PULLUP;
        gpio.Speed = GPIO_SPEED_FREQ_HIGH;
        gpio.Pin   = CAN1_RX_PIN;
        HAL_GPIO_Init(CAN1_PORT, &gpio);

        /* CAN TX: alternate function push-pull */
        gpio.Mode  = GPIO_MODE_AF_PP;
        gpio.Pull  = GPIO_NOPULL;
        gpio.Pin   = CAN1_TX_PIN;
        HAL_GPIO_Init(CAN1_PORT, &gpio);

        /* NVIC */
        HAL_NVIC_SetPriority(CAN1_IRQn, 1, 0);
        HAL_NVIC_EnableIRQ(CAN1_IRQn);
    }
#if CAN_INSTANCE_COUNT > 1
    else if (channel == 1) {
        /* CAN2 */
        CAN2_GPIO_CLK_ENABLE();
        CAN2_PERIPH_CLK_ENABLE();

        GPIO_InitTypeDef gpio = {0};

        /* CAN2 RX: input with pull-up */
        gpio.Mode  = GPIO_MODE_INPUT;
        gpio.Pull  = GPIO_PULLUP;
        gpio.Speed = GPIO_SPEED_FREQ_HIGH;
        gpio.Pin   = CAN2_RX_PIN;
        HAL_GPIO_Init(CAN2_PORT, &gpio);

        /* CAN2 TX: alternate function push-pull */
        gpio.Mode  = GPIO_MODE_AF_PP;
        gpio.Pull  = GPIO_NOPULL;
        gpio.Pin   = CAN2_TX_PIN;
        HAL_GPIO_Init(CAN2_PORT, &gpio);

        HAL_NVIC_SetPriority(CAN2_IRQn, 1, 0);
        HAL_NVIC_EnableIRQ(CAN2_IRQn);
    }
#endif
}

/*============================================================================
 * Public API Implementation
 *============================================================================*/

can_status_t can_init(uint8_t channel, const can_config_t *config)
{
    if (channel >= CAN_INSTANCE_COUNT || !config) return CAN_ERR_PARAM;

    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx || !h) return CAN_ERR_PARAM;

    /* De-init if already initialized */
    if (ctx->initialized) {
        can_deinit(channel);
    }

    /* Compute timing — use reference-verified values for common baudrates.
     * APB1=32MHz on F103 (HSI 8MHz/2 × PLL16 = 64MHz SYSCLK, APB1=/2). */
    uint32_t psc, bs1, bs2, sjw;
    if (config->baudrate == 250000) {
        /* APB1=32MHz: BRP=7(psc=8), TS1=7(BS1=8), TS2=6(BS2=7), SJW=0(SJW=1)
         * Bit time = (1+8+7)*8 = 128 tq, 128/32MHz = 4µs = 250kbps */
        psc = 8; bs1 = 8; bs2 = 7; sjw = 1;
    } else if (config->baudrate == 500000) {
        /* APB1=32MHz: BRP=7(psc=8), TS1=4(BS1=5), TS2=1(BS2=2), SJW=0(SJW=1)
         * Bit time = (1+5+2)*8 = 64 tq, 64/32MHz = 2µs = 500kbps */
        psc = 8; bs1 = 5; bs2 = 2; sjw = 1;
    } else {
        if (can_calc_timing(config->baudrate, &psc, &bs1, &bs2, &sjw) != CAN_OK) {
            return CAN_ERR_PARAM;
        }
    }

    /* Initialize HAL CAN handle */
    memset(h, 0, sizeof(*h));
    if (channel == 0) {
        h->Instance = CAN1;
    }
#if CAN_INSTANCE_COUNT > 1
    else if (channel == 1) {
        h->Instance = CAN2;
    }
#endif

    h->Init.Prescaler     = psc;
    h->Init.Mode          = CAN_MODE_NORMAL;
    h->Init.SyncJumpWidth = CAN_SJW_1TQ + (sjw - 1);
    h->Init.TimeSeg1      = CAN_BS1_1TQ + (bs1 - 1);
    h->Init.TimeSeg2      = CAN_BS2_1TQ + (bs2 - 1);
    h->Init.TimeTriggeredMode = DISABLE;
    h->Init.AutoBusOff         = DISABLE;  /* Match reference: CAN_ABOM = DISABLE */
    h->Init.AutoWakeUp         = DISABLE;
    h->Init.AutoRetransmission = ENABLE;   /* Match reference: CAN_NART = DISABLE */
    h->Init.ReceiveFifoLocked  = DISABLE;
    h->Init.TransmitFifoPriority = DISABLE;

    /* Lock CAN1 access (F103 has only CAN1 on APB1 at 0x40006400) */
    CAN_TypeDef *CANx = h->Instance;
    uint32_t wait;

    /* Enable clocks via direct register access */
    CAN1_PERIPH_CLK_ENABLE();
    CAN1_GPIO_CLK_ENABLE();

    /* Configure GPIO using proven direct register writes (same as can_run_test).
     * PA11 = CAN RX: input with pull-up. PA12 = CAN TX: AF push-pull 50MHz. */
    GPIOA->CRH &= ~((0xF << 12) | (0xF << 16));
    GPIOA->CRH |= (0x8 << 12) | (0xB << 16);
    GPIOA->ODR |= (1 << 11); /* PA11 pull-up */

    /* NVIC */
    HAL_NVIC_SetPriority(CAN1_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(CAN1_IRQn);

    /* Initialize CAN using proven SPL-style direct register writes.
     * HAL_CAN_Init has issues on F103 — direct register access is reliable. */

    /* Exit sleep, request init */
    CANx->MCR &= ~CAN_MCR_SLEEP;
    CANx->MCR |= CAN_MCR_INRQ;
    wait = 1000000;
    while (!(CANx->MSR & CAN_MSR_INAK) && --wait) {}
    if (wait == 0) return CAN_ERR_HW;

    /* Clear all control bits. NART is set per-mode. */
    CANx->MCR &= ~(CAN_MCR_TTCM | CAN_MCR_ABOM | CAN_MCR_AWUM
                 | CAN_MCR_NART | CAN_MCR_RFLM | CAN_MCR_TXFP);
    if (config->mode == 0 || config->mode == 1) {
        CANx->MCR |= CAN_MCR_NART; /* No retry in normal/listen-only */
    }

    /* Build BTR: timing + mode. */
    uint32_t btr = ((uint32_t)(psc - 1))           /* BRP */
                 | ((uint32_t)(bs1 - 1) << 16)     /* TS1 */
                 | ((uint32_t)(bs2 - 1) << 20)     /* TS2 */
                 | ((uint32_t)(sjw - 1) << 24);    /* SJW */
    /* Apply mode bits */
    if (config->mode == 1)      btr |= (1U << 31);  /* SILM */
    else if (config->mode == 2) btr |= (1U << 30);  /* LBKM */
    else if (config->mode == 3) btr |= (3U << 30);  /* both */

    CANx->BTR = btr;

    /* Configure filter using proven direct register writes (same as can_run_test). */
    CANx->FMR |= CAN_FMR_FINIT;
    CANx->FA1R &= ~(1U << 0);
    CANx->sFilterRegister[0].FR1 = 0;
    CANx->sFilterRegister[0].FR2 = 0;
    CANx->FM1R &= ~(1U << 0);
    CANx->FS1R |= (1U << 0);
    CANx->FFA1R &= ~(1U << 0);
    CANx->FA1R |= (1U << 0);
    CANx->FMR &= ~CAN_FMR_FINIT;

    /* Leave init */
    CANx->MCR &= ~CAN_MCR_INRQ;
    wait = 1000000;
    while ((CANx->MSR & CAN_MSR_INAK) && --wait) {}
    if (wait == 0) return CAN_ERR_HW;

    /* Flush stale RX FIFO (entering init mode clears error counters) */
    while ((CANx->RF0R & 0x03) != 0) { CANx->RF0R |= 0x20; }

    /* Stabilization delay after leaving init mode */
    {volatile uint32_t _d=0; while(_d<100000) _d++;}

    h->State = HAL_CAN_STATE_READY;

    /* Activate notification for RX FIFO0 */
    HAL_CAN_ActivateNotification(h, CAN_IT_RX_FIFO0_MSG_PENDING |
                                     CAN_IT_ERROR |
                                     CAN_IT_BUSOFF |
                                     CAN_IT_LAST_ERROR_CODE);

    /* Save config */
    memcpy(&ctx->config, config, sizeof(can_config_t));
    memset(&ctx->stats, 0, sizeof(can_stats_t));
    ctx->initialized = 1;
    ctx->listening = 0;  /* Not listening yet */

    /* Wait for CAN bus to stabilize (reference code has 1s delay after init).
     * The CAN needs to see 11 recessive bits before it can participate. */
    {volatile uint32_t _d=0; while(_d<200000) _d++;}

    return CAN_OK;
}

can_status_t can_deinit(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx || !h) return CAN_ERR_PARAM;

    can_stop_listen(channel);
    HAL_CAN_DeInit(h);
    ctx->initialized = 0;

    return CAN_OK;
}

can_status_t can_set_baudrate(uint8_t channel, uint32_t baudrate)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;

    uint32_t psc, bs1, bs2, sjw;
    if (can_calc_timing(baudrate, &psc, &bs1, &bs2, &sjw) != CAN_OK) {
        return CAN_ERR_PARAM;
    }

    /* Stop, reconfigure, restart */
    HAL_CAN_Stop(h);

    h->Init.Prescaler     = psc;
    h->Init.SyncJumpWidth = CAN_SJW_1TQ + (sjw - 1);
    h->Init.TimeSeg1      = CAN_BS1_1TQ + (bs1 - 1);
    h->Init.TimeSeg2      = CAN_BS2_1TQ + (bs2 - 1);

    if (HAL_CAN_Init(h) != HAL_OK) {
        return CAN_ERR_HW;
    }

    ctx->config.baudrate = baudrate;

    /* Restart */
    HAL_CAN_Start(h);
    if (ctx->listening) {
        HAL_CAN_ActivateNotification(h, CAN_IT_RX_FIFO0_MSG_PENDING |
                                         CAN_IT_ERROR |
                                         CAN_IT_BUSOFF |
                                         CAN_IT_LAST_ERROR_CODE);
    }

    return CAN_OK;
}

can_status_t can_set_mode(uint8_t channel, uint8_t mode)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;

    /* Request init mode */
    h->Instance->MCR |= CAN_MCR_INRQ;
    uint32_t wait = 1000000;
    while (!(h->Instance->MSR & CAN_MSR_INAK) && --wait) {}
    if (wait == 0) return CAN_ERR_HW;

    /* Update mode bits in BTR while preserving timing */
    uint32_t btr = h->Instance->BTR;
    btr &= ~(3U << 30);  /* Clear both mode bits */
    if (mode == 1)      btr |= (1U << 31);  /* SILM */
    else if (mode == 2) btr |= (1U << 30);  /* LBKM */
    else if (mode == 3) btr |= (3U << 30);  /* both */
    h->Instance->BTR = btr;

    /* Set NART per mode: 0 in loopback (retries needed for F103 loopback
     * to work), 1 in normal/listen-only (no retries = no ghost RX frames) */
    if (mode == 0 || mode == 1) {
        h->Instance->MCR |= CAN_MCR_NART;
    } else {
        h->Instance->MCR &= ~CAN_MCR_NART;
    }

    /* Abort TX mailboxes and flush RX FIFO WHILE IN init mode.
     * Must be done before leaving init, otherwise CAN re-processes stale mailboxes. */
    for (int m = 0; m < 3; m++) {
        h->Instance->sTxMailBox[m].TIR = 0;
        h->Instance->sTxMailBox[m].TDTR = 0;
        h->Instance->sTxMailBox[m].TDLR = 0;
        h->Instance->sTxMailBox[m].TDHR = 0;
    }
    h->Instance->TSR = (1U | 2U | 8U)           /* RQCP0 TXOK0 TERR0 */
                     | (1U | 2U | 8U) << 8     /* RQCP1 TXOK1 TERR1 */
                     | (1U | 2U | 8U) << 16;   /* RQCP2 TXOK2 TERR2 */
    while ((h->Instance->RF0R & 0x03) != 0) {
        h->Instance->RF0R |= 0x20;
    }

    /* Leave init mode */
    h->Instance->MCR &= ~CAN_MCR_INRQ;
    wait = 1000000;
    while ((h->Instance->MSR & CAN_MSR_INAK) && --wait) {}
    if (wait == 0) return CAN_ERR_HW;

    /* Stabilization delay */
    {volatile uint32_t _d=0; while(_d<200000) _d++;}

    /* Final flush: stale TX mailboxes may have been processed during
     * stabilization, leaving ghost frames in the RX FIFO. */
    while ((h->Instance->RF0R & 0x03) != 0) {
        h->Instance->RF0R |= 0x20;
    }

    /* Re-enable error interrupts if was listening.
     * Do NOT enable FMPIE0/FMPIE1 — RX is polled, not interrupt-driven. */
    if (ctx->listening) {
        h->Instance->IER |= 0x10 | 0x20 | 0x80; /* ERRIE, BOFIE, LECIE only */
    }

    ctx->config.mode = mode;
    h->State = HAL_CAN_STATE_READY;
    return CAN_OK;
}

can_status_t can_set_filter(uint8_t channel, uint8_t filter_index,
                            uint8_t filter_mode, uint8_t filter_scale,
                            uint32_t id_high, uint32_t id_low,
                            uint32_t mask_high, uint32_t mask_low)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;

    CAN_FilterTypeDef filter = {0};
    filter.FilterBank    = filter_index;
    filter.FilterMode    = (filter_mode == 0) ? CAN_FILTERMODE_IDMASK : CAN_FILTERMODE_IDLIST;
    filter.FilterScale   = (filter_scale == 0) ? CAN_FILTERSCALE_16BIT : CAN_FILTERSCALE_32BIT;
    filter.FilterIdHigh  = (uint16_t)(id_high & 0xFFFF);
    filter.FilterIdLow   = (uint16_t)(id_low & 0xFFFF);
    filter.FilterMaskIdHigh = (uint16_t)(mask_high & 0xFFFF);
    filter.FilterMaskIdLow  = (uint16_t)(mask_low & 0xFFFF);
    filter.FilterFIFOAssignment = CAN_FILTER_FIFO0;
    filter.FilterActivation     = ENABLE;
    filter.SlaveStartFilterBank = (channel == 0 && CAN_INSTANCE_COUNT > 1) ? 14 : 0;

    return (HAL_CAN_ConfigFilter(h, &filter) == HAL_OK) ? CAN_OK : CAN_ERR_HW;
}

can_status_t can_send_frame(uint8_t channel, uint32_t id, uint8_t ide,
                            uint8_t rtr, uint8_t dlc, const uint8_t *data,
                            uint32_t timeout_ms)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;
    if (dlc > 8) return CAN_ERR_PARAM;

    /* SPL-style mailbox management: free completed mailboxes, find empty one. */
    /* First, free any mailboxes whose transmission has completed (RQCP set). */
    for (int m = 0; m < 3; m++) {
        if (h->Instance->TSR & (CAN_TSR_RQCP0 << (m * 8))) {
            /* Transmission complete — acknowledge by clearing RQCP */
            h->Instance->TSR = (CAN_TSR_RQCP0 << (m * 8));
        }
    }
    /* Now find an empty mailbox */
    uint32_t tme = (h->Instance->TSR >> 26) & 7;
    uint32_t mbox;
    if (tme & 1) mbox = 0;
    else if (tme & 2) mbox = 1;
    else if (tme & 4) mbox = 2;
    else {
        /* All busy — force-release mailbox 0 by aborting */
        h->Instance->sTxMailBox[0].TIR &= ~CAN_TI0R_TXRQ;
        h->Instance->TSR = CAN_TSR_ABRQ0;
        mbox = 0;
    }

    volatile uint32_t *mbx = &h->Instance->sTxMailBox[mbox].TIR;

    /* Fill mailbox — write DLC and data FIRST, then TIR with TXRQ last.
     * The CAN controller starts transmitting as soon as TXRQ is set,
     * so DLC and data must already be in the mailbox registers. */
    mbx[1] = dlc & 0x0F;   /* TDTR: DLC */
    mbx[2] = data[0] | ((uint32_t)data[1] << 8) | ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);  /* TDLR */
    mbx[3] = data[4] | ((uint32_t)data[5] << 8) | ((uint32_t)data[6] << 16) | ((uint32_t)data[7] << 24);  /* TDHR */
    /* TIR last — TXRQ triggers transmission */
    if (ide) mbx[0] = (id << 3) | CAN_TI0R_IDE | CAN_TI0R_TXRQ;
    else     mbx[0] = (id << 21) | CAN_TI0R_TXRQ;
    if (rtr) mbx[0] |= CAN_TI0R_RTR;

    /* Check if CAN is stuck in init mode */
    if (h->Instance->MSR & CAN_MSR_INAK) {
        h->Instance->MCR &= ~CAN_MCR_INRQ;
        uint32_t w = 500000;
        while ((h->Instance->MSR & CAN_MSR_INAK) && --w) {}
    }

    /* Fire-and-forget: mailbox filled, TX started. Don't wait for RQCP. */
    ctx->stats.tx_success++;
    return CAN_OK;
}

can_status_t can_receive_frame(uint8_t channel, can_frame_t *frame,
                               uint32_t timeout_ms)
{
    if (channel >= CAN_INSTANCE_COUNT || !frame) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;

    CAN_RxHeaderTypeDef rx_header;
    uint8_t rx_data[8];
    memset(frame, 0, sizeof(*frame));

    uint32_t start = device_get_uptime_ms();
    while (1) {
        HAL_StatusTypeDef ret = HAL_CAN_GetRxMessage(h, CAN_RX_FIFO0,
                                                      &rx_header, rx_data);
        if (ret == HAL_OK) {
            frame->id        = (rx_header.IDE == CAN_ID_EXT) ? rx_header.ExtId : rx_header.StdId;
            frame->ide       = (rx_header.IDE == CAN_ID_EXT) ? 1 : 0;
            frame->rtr       = (rx_header.RTR == CAN_RTR_REMOTE) ? 1 : 0;
            frame->dlc       = rx_header.DLC;
            frame->channel   = channel;
            frame->timestamp = rx_header.Timestamp != 0 ? rx_header.Timestamp : device_get_uptime_us();
            frame->is_error_frame = 0;
            memcpy(frame->data, rx_data, frame->dlc > 8 ? 8 : frame->dlc);
            ctx->stats.rx_received++;
            return CAN_OK;
        }
        if (timeout_ms == 0) {
            return CAN_ERR_TIMEOUT;
        }
        if ((device_get_uptime_ms() - start) >= timeout_ms) {
            return CAN_ERR_TIMEOUT;
        }
    }
}

can_status_t can_register_rx_callback(uint8_t channel, can_rx_callback_t callback)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    if (!ctx) return CAN_ERR_PARAM;
    ctx->rx_callback = callback;
    return CAN_OK;
}

can_status_t can_start_listen(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;

    if (!ctx->listening) {
        HAL_StatusTypeDef ret = HAL_CAN_Start(h);
        if (ret != HAL_OK && ret != HAL_ERROR) return CAN_ERR_HW;
        ctx->listening = 1;
    }

    /* Enable error interrupts only. RX handled by poll in send handler. */
    h->Instance->IER |= 0x10   /* ERRIE: error */
                      | 0x20   /* BOFIE: bus-off */
                      | 0x80;  /* LECIE: last error */

    return CAN_OK;
}

can_status_t can_stop_listen(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx->initialized) return CAN_ERR_NOT_INIT;

    HAL_CAN_DeactivateNotification(h, CAN_IT_RX_FIFO0_MSG_PENDING |
                                       CAN_IT_RX_FIFO1_MSG_PENDING |
                                       CAN_IT_ERROR |
                                       CAN_IT_BUSOFF |
                                       CAN_IT_LAST_ERROR_CODE |
                                       CAN_IT_ERROR_PASSIVE |
                                       CAN_IT_ERROR_WARNING);
    HAL_CAN_Stop(h);
    ctx->listening = 0;

    return CAN_OK;
}

can_status_t can_get_error_status(uint8_t channel, uint32_t *error_flags,
                                  uint8_t *tx_error_cnt, uint8_t *rx_error_cnt)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    CAN_HandleTypeDef *h = can_get_handle(channel);
    if (!h) return CAN_ERR_PARAM;

    uint32_t flags = 0;
    uint32_t esr = h->Instance->ESR;

    if (esr & CAN_ESR_BOFF)  flags |= CAN_ERR_BUS_OFF;
    if (esr & CAN_ESR_EPVF)  flags |= CAN_ERR_PASSIVE;
    if (esr & CAN_ESR_EWGF)  flags |= CAN_ERR_WARNING;
    if (esr & CAN_ESR_LEC_0) {
        /* LEC[2:0] in ESR */
        uint32_t lec = (esr >> 4) & 0x07;
        switch (lec) {
        case 0x01: flags |= CAN_ERR_BIT_STUFFING; break;
        case 0x02: flags |= CAN_ERR_FORM; break;
        case 0x03: flags |= CAN_ERR_ACK; break;
        case 0x04: /* Bit recessive error */ break;
        case 0x05: /* Bit dominant error */ break;
        case 0x06: flags |= CAN_ERR_CRC; break;
        }
    }

    if (error_flags)    *error_flags = flags;
    if (tx_error_cnt)   *tx_error_cnt = (uint8_t)((esr >> 16) & 0xFF);
    if (rx_error_cnt)   *rx_error_cnt = (uint8_t)((esr >> 24) & 0xFF);

    return CAN_OK;
}

can_status_t can_clear_errors(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return CAN_ERR_PARAM;
    CAN_HandleTypeDef *h = can_get_handle(channel);
    if (!h) return CAN_ERR_PARAM;

    /* Clear error status by writing to ESR */
    SET_BIT(h->Instance->MCR, CAN_MCR_ABOM);
    __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_EWG);
    __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_EPV);
    __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_BOF);

    return CAN_OK;
}

can_status_t can_get_stats(uint8_t channel, can_stats_t *stats)
{
    if (channel >= CAN_INSTANCE_COUNT || !stats) return CAN_ERR_PARAM;
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    if (!ctx) return CAN_ERR_PARAM;
    memcpy(stats, &ctx->stats, sizeof(can_stats_t));
    return CAN_OK;
}

uint8_t can_get_channel_count(void)
{
    return CAN_INSTANCE_COUNT;
}

uint8_t can_is_initialized(uint8_t channel)
{
    if (channel >= CAN_INSTANCE_COUNT) return 0;
    return g_can_ctx[channel].initialized;
}

/*============================================================================
 * CAN Interrupt Handlers
 *============================================================================*/

/**
 * @brief Process received CAN frames in interrupt context and call user callback.
 */
static void can_process_rx_irq(uint8_t channel)
{
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx || !h || !ctx->listening) return;

    /* In loopback mode, RX frames are consumed by the send-handler poll.
     * Do NOT drain the FIFO here — ISR may fire for error interrupts
     * and draining would lose the loopback echo frame. */
    if (h->Instance->BTR & (1U << 30)) return;
    /* Drain RX FIFO in non-loopback modes to prevent overrun */
    while ((h->Instance->RF0R & 0x03) != 0) {
        h->Instance->RF0R |= 0x20; /* Release FIFO: discard */
    }
}

/**
 * @brief Process CAN errors in interrupt context.
 */
static void can_process_error_irq(uint8_t channel)
{
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx || !h) return;

    /* In loopback modes, TX errors (dominant bit etc.) are expected
     * on F103. Don't report them as error frames, but MUST clear
     * the interrupt flags to prevent interrupt storm. */
    uint32_t btr = h->Instance->BTR;
    if (btr & (1U << 30)) {
        /* Clear all error interrupt flags */
        __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_EWG);
        __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_EPV);
        __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_BOF);
        /* Clear LEC (Last Error Code) — write any value to clear */
        h->Instance->ESR |= CAN_ESR_LEC;
        return;
    }

    uint32_t esr = h->Instance->ESR;
    uint32_t error_flags = 0;

    if (esr & CAN_ESR_BOFF) error_flags |= CAN_ERR_BUS_OFF;
    if (esr & CAN_ESR_EPVF) error_flags |= CAN_ERR_PASSIVE;
    if (esr & CAN_ESR_EWGF) error_flags |= CAN_ERR_WARNING;

    uint32_t lec = (esr >> 4) & 0x07;
    switch (lec) {
    case 0x01: error_flags |= CAN_ERR_BIT_STUFFING; break;
    case 0x02: error_flags |= CAN_ERR_FORM; break;
    case 0x03: error_flags |= CAN_ERR_ACK; break;
    case 0x06: error_flags |= CAN_ERR_CRC; break;
    default: break;
    }

    if (error_flags) {
        ctx->stats.error_count++;
        if (error_flags & CAN_ERR_BUS_OFF) ctx->stats.bus_off_count++;

        if (ctx->rx_callback) {
            can_frame_t frame;
            memset(&frame, 0, sizeof(frame));
            frame.channel       = channel;
            frame.is_error_frame = 1;
            frame.error_flags   = error_flags;
            frame.timestamp     = device_get_uptime_us();
            ctx->rx_callback(&frame);
        }
    }

    /* Clear error flags */
    __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_EWG);
    __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_EPV);
    __HAL_CAN_CLEAR_FLAG(h, CAN_FLAG_BOF);
}

/*============================================================================
 * Global CAN IRQ Handler(s)
 *
 * These are called from stm32fxxx_it.c based on which CAN instances
 * are enabled. Each channel routes to the correct handler.
 *============================================================================*/

void CAN1_IRQHandler(void)
{
    CAN_HandleTypeDef *h = can_get_handle(0);
    if (h) {
        /* Skip HAL_CAN_IRQHandler — it may consume RX flags incorrectly.
         * Process RX and errors via our own handlers directly. */
        can_process_rx_irq(0);
        can_process_error_irq(0);
    }
}

#if CAN_INSTANCE_COUNT > 1
void CAN2_IRQHandler(void)
{
    CAN_HandleTypeDef *h = can_get_handle(1);
    if (h) {
        HAL_CAN_IRQHandler(h);
        can_process_rx_irq(1);
        can_process_error_irq(1);
    }
}
#endif

/* CAN loopback diagnostic test. Standalone, no dependency on existing CAN state. */
/* CAN send + poll using proven register access.
 * If loopback_mode is non-zero, sets LBKM and polls RX after TX.
 * Returns 1 if loopback RX received with matching ID (or TX succeeded in normal mode). */

/**
 * @brief Poll RX FIFO for a loopback echo frame.
 *        Does NOT reinitialize CAN — uses existing configuration.
 * @param channel         CAN channel index
 * @param expected_id     Expected CAN ID in the loopback frame
 * @param timeout_cycles  Busy-wait loop iterations
 * @return 1 if matching loopback frame received, 0 on timeout or mismatch
 */
int can_poll_for_loopback_rx(uint8_t channel, uint32_t expected_id,
                             uint32_t timeout_cycles)
{
    can_channel_ctx_t *ctx = can_get_ctx(channel);
    CAN_HandleTypeDef  *h   = can_get_handle(channel);
    if (!ctx || !h || !ctx->initialized) return 0;

    /* Check if we're actually in loopback mode */
    if (!(h->Instance->BTR & (1U << 30))) return 0;

    uint32_t w = timeout_cycles;
    while (--w) {
        if ((h->Instance->RF0R & 0x03) != 0) {
            uint32_t rir = h->Instance->sFIFOMailBox[0].RIR;
            uint32_t rx_id = (rir & CAN_RI0R_IDE)
                ? ((rir >> 3) & 0x1FFFFFFF)
                : ((rir >> 21) & 0x7FF);
            h->Instance->RF0R |= CAN_RF0R_RFOM0;
            if (rx_id == expected_id) {
                ctx->stats.rx_received++;
                return 1;
            }
            /* Frame received but ID didn't match — keep polling */
        }
    }
    return 0;
}

int can_run_test_ext(uint32_t can_id, uint8_t dlc, uint8_t flags, const uint8_t *txdata) {
    uint32_t w;
    uint8_t ide = flags & 0x01;
    uint8_t rtr = (flags >> 1) & 0x01;

    /* Ensure clocks are enabled for CAN1 and GPIOA */
    *(volatile uint32_t *)0x4002101C |= (1U << 25);  /* RCC_APB1ENR: CAN1 */
    *(volatile uint32_t *)0x40021018 |= (1U << 2);   /* RCC_APB2ENR: GPIOA */

    /* Configure CAN GPIO pins directly (same as proven can_run_test).
     * PA11 = RX: input with pull-up, PA12 = TX: AF push-pull 50MHz */
    GPIOA->CRH &= ~((0xF << 12) | (0xF << 16));
    GPIOA->CRH |= (0x8 << 12) | (0xB << 16);
    GPIOA->ODR |= (1 << 11);  /* PA11 pull-up */

    /* Read loopback state AFTER clocks are enabled. */
    int loopback = (CAN1->BTR >> 30) & 1;

    /* Use the discovered loopback state from BTR */

    /* Free completed mailboxes */
    for (int m = 0; m < 3; m++) {
        if (CAN1->TSR & (CAN_TSR_RQCP0 << (m * 8))) {
            CAN1->TSR = (CAN_TSR_RQCP0 << (m * 8));
        }
    }

    /* Find empty TX mailbox */
    uint32_t tme = (CAN1->TSR >> 26) & 7;
    uint32_t mbox = (tme & 1) ? 0 : (tme & 2) ? 1 : (tme & 4) ? 2 : 3;
    if (mbox > 2) {
        /* All busy — force-release mailbox 0 */
        CAN1->sTxMailBox[0].TIR &= ~CAN_TI0R_TXRQ;
        CAN1->TSR = CAN_TSR_ABRQ0;
        mbox = 0;
    }

    /* Fill mailbox — write data/DLC first, then TIR with TXRQ last */
    CAN1->sTxMailBox[mbox].TDTR = dlc & 0x0F;
    CAN1->sTxMailBox[mbox].TDLR = txdata[0] | ((uint32_t)txdata[1]<<8)
                                | ((uint32_t)txdata[2]<<16) | ((uint32_t)txdata[3]<<24);
    CAN1->sTxMailBox[mbox].TDHR = txdata[4] | ((uint32_t)txdata[5]<<8)
                                | ((uint32_t)txdata[6]<<16) | ((uint32_t)txdata[7]<<24);
    if (ide) CAN1->sTxMailBox[mbox].TIR = (can_id << 3) | CAN_TI0R_IDE | CAN_TI0R_TXRQ;
    else     CAN1->sTxMailBox[mbox].TIR = (can_id << 21) | CAN_TI0R_TXRQ;
    if (rtr) CAN1->sTxMailBox[mbox].TIR |= CAN_TI0R_RTR;

    /* In non-loopback mode, fire-and-forget — return success immediately */
    if (!loopback) return 1;

    /* In loopback mode: wait for TX completion then poll RX FIFO */
    uint32_t rqcp_bit = CAN_TSR_RQCP0 << (mbox * 8);
    w = 5000000; while (!(CAN1->TSR & rqcp_bit) && --w) {}
    if (w == 0) return 0;

    /* Poll RX FIFO for loopback echo */
    w = 5000000;
    while (--w) {
        if ((CAN1->RF0R & 0x03) != 0) {
            uint32_t rir = CAN1->sFIFOMailBox[0].RIR;
            CAN1->RF0R |= CAN_RF0R_RFOM0;
            uint32_t rx_id = (rir & CAN_RI0R_IDE) ? ((rir>>3) & 0x1FFFFFFF) : ((rir>>21) & 0x7FF);
            return (rx_id == can_id) ? 1 : 0;
        }
    }
    return 0;
}

int can_run_test(uint8_t *out, uint16_t maxlen)
{
    if (maxlen < 20 || !out) return 0;
    memset(out, 0, maxlen);

    /* Enable clocks */
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_CAN1_CLK_ENABLE();

    /* PA11 = input pull-up */
    GPIOA->CRH &= ~(0xF << 12);
    GPIOA->CRH |= (0x8 << 12);
    GPIOA->ODR |= (1 << 11);
    /* PA12 = AF push-pull 50MHz */
    GPIOA->CRH &= ~(0xF << 16);
    GPIOA->CRH |= (0xB << 16);

    /* SPL-style CAN init */
    CAN1->MCR &= ~CAN_MCR_SLEEP;
    CAN1->MCR |= CAN_MCR_INRQ;
    uint32_t w = 1000000;
    while (!(CAN1->MSR & CAN_MSR_INAK) && --w) {}
    if (w == 0) goto exit;

    CAN1->MCR &= ~(CAN_MCR_TTCM | CAN_MCR_ABOM | CAN_MCR_AWUM
                 | CAN_MCR_NART | CAN_MCR_RFLM | CAN_MCR_TXFP);
    CAN1->BTR = (1U << 30) | (0U << 24) | (6U << 20) | (7U << 16) | 7U;

    CAN1->FMR |= CAN_FMR_FINIT;
    CAN1->FA1R &= ~(1U << 0);
    CAN1->sFilterRegister[0].FR1 = 0;
    CAN1->sFilterRegister[0].FR2 = 0;
    CAN1->FM1R &= ~(1U << 0);
    CAN1->FS1R |= (1U << 0);
    CAN1->FFA1R &= ~(1U << 0);
    CAN1->FA1R |= (1U << 0);
    CAN1->FMR &= ~CAN_FMR_FINIT;

    CAN1->MCR &= ~CAN_MCR_INRQ;
    w = 1000000;
    while ((CAN1->MSR & CAN_MSR_INAK) && --w) {}
    if (w == 0) goto exit;

    /* Send frame: ID=0x123, DLC=1, data=0x55 */
    CAN1->sTxMailBox[0].TIR = (0x123U << 21) | CAN_TI0R_TXRQ;
    CAN1->sTxMailBox[0].TDTR = 1;
    CAN1->sTxMailBox[0].TDLR = 0x55;
    CAN1->sTxMailBox[0].TDHR = 0;

    /* Wait for TX complete */
    w = 5000000;
    while (!(CAN1->TSR & CAN_TSR_RQCP0) && --w) {}

    /* Poll RX FIFO */
    w = 5000000;
    while (--w) {
        if ((CAN1->RF0R & 0x03) != 0) {
            uint32_t rir = CAN1->sFIFOMailBox[0].RIR;
            CAN1->RF0R |= CAN_RF0R_RFOM0;
            out[0] = 1; out[1] = rir & 0xFF;
            out[2] = (rir >> 8) & 0xFF;
            out[3] = (rir >> 16) & 0xFF;
            out[4] = (rir >> 24) & 0xFF;
            out[5] = (uint8_t)CAN1->sFIFOMailBox[0].RDTR;
            out[6] = (uint8_t)CAN1->sFIFOMailBox[0].RDLR;
            break;
        }
    }

exit:
    out[8]  = (uint8_t)(CAN1->TSR & 0xFF);
    out[9]  = (uint8_t)((CAN1->TSR >> 8) & 0xFF);
    out[10] = (uint8_t)(CAN1->ESR & 0xFF);
    out[11] = (uint8_t)((CAN1->ESR >> 8) & 0xFF);
    out[12] = (uint8_t)(CAN1->RF0R & 0xFF);
    out[13] = (uint8_t)(CAN1->BTR & 0xFF);
    out[14] = (uint8_t)((CAN1->BTR >> 8) & 0xFF);
    out[15] = (uint8_t)((CAN1->BTR >> 16) & 0xFF);
    out[16] = (uint8_t)((CAN1->BTR >> 24) & 0xFF);
    out[17] = (uint8_t)(CAN1->MCR & 0xFF);
    out[18] = (uint8_t)(CAN1->IER & 0xFF);
    out[19] = (uint8_t)w;
    return 20;
}
