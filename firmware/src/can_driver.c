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
        gpio.Mode  = GPIO_MODE_AF_PP;
        gpio.Pull  = GPIO_PULLUP;
        gpio.Speed = GPIO_SPEED_FREQ_HIGH;
        gpio.Pin   = CAN1_RX_PIN;
        HAL_GPIO_Init(CAN1_PORT, &gpio);

        gpio.Mode  = GPIO_MODE_AF_PP;
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
        gpio.Mode  = GPIO_MODE_AF_PP;
        gpio.Pull  = GPIO_PULLUP;
        gpio.Speed = GPIO_SPEED_FREQ_HIGH;
        gpio.Pin   = CAN2_RX_PIN;
        HAL_GPIO_Init(CAN2_PORT, &gpio);

        gpio.Mode  = GPIO_MODE_AF_PP;
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

    /* Compute timing */
    uint32_t psc, bs1, bs2, sjw;
    if (can_calc_timing(config->baudrate, &psc, &bs1, &bs2, &sjw) != CAN_OK) {
        return CAN_ERR_PARAM;
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
    h->Init.AutoBusOff         = ENABLE;
    h->Init.AutoWakeUp         = DISABLE;
    h->Init.AutoRetransmission = ENABLE;
    h->Init.ReceiveFifoLocked  = DISABLE;
    h->Init.TransmitFifoPriority = DISABLE;

    /* MSP init (pins, clock, NVIC) */
    can_msp_init(channel);

    if (HAL_CAN_Init(h) != HAL_OK) {
        return CAN_ERR_HW;
    }

    /* Start in requested mode */
    can_set_mode(channel, config->mode);

    /* Configure default filter (accept all) */
    CAN_FilterTypeDef filter = {0};
    filter.FilterBank = 0;
    filter.FilterMode = CAN_FILTERMODE_IDMASK;
    filter.FilterScale = CAN_FILTERSCALE_32BIT;
    filter.FilterIdHigh   = 0;
    filter.FilterIdLow    = 0;
    filter.FilterMaskIdHigh = 0;
    filter.FilterMaskIdLow  = 0;
    filter.FilterFIFOAssignment = CAN_FILTER_FIFO0;
    filter.FilterActivation = ENABLE;
    filter.SlaveStartFilterBank = (channel == 0 && CAN_INSTANCE_COUNT > 1) ? 14 : 0;

    HAL_CAN_ConfigFilter(h, &filter);

    /* Activate notification for RX FIFO0 */
    HAL_CAN_ActivateNotification(h, CAN_IT_RX_FIFO0_MSG_PENDING |
                                     CAN_IT_ERROR |
                                     CAN_IT_BUSOFF |
                                     CAN_IT_LAST_ERROR_CODE);

    /* Save config */
    memcpy(&ctx->config, config, sizeof(can_config_t));
    memset(&ctx->stats, 0, sizeof(can_stats_t));
    ctx->initialized = 1;
    ctx->listening = 0;

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

    /* Stop current operation */
    HAL_CAN_Stop(h);

    switch (mode) {
    case 0: h->Init.Mode = CAN_MODE_NORMAL; break;
    case 1: h->Init.Mode = CAN_MODE_SILENT; break;      /* Listen only */
    case 2: h->Init.Mode = CAN_MODE_LOOPBACK; break;
    case 3: h->Init.Mode = CAN_MODE_SILENT_LOOPBACK; break;
    default: return CAN_ERR_PARAM;
    }

    if (HAL_CAN_Init(h) != HAL_OK) {
        return CAN_ERR_HW;
    }

    /* Restart */
    HAL_CAN_Start(h);
    if (ctx->listening) {
        HAL_CAN_ActivateNotification(h, CAN_IT_RX_FIFO0_MSG_PENDING |
                                         CAN_IT_ERROR |
                                         CAN_IT_BUSOFF |
                                         CAN_IT_LAST_ERROR_CODE);
    }

    ctx->config.mode = mode;
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

    CAN_TxHeaderTypeDef tx_header = {0};
    tx_header.StdId    = (ide == 0) ? id : 0;
    tx_header.ExtId    = (ide == 1) ? id : 0;
    tx_header.IDE      = (ide == 1) ? CAN_ID_EXT : CAN_ID_STD;
    tx_header.RTR      = (rtr == 1) ? CAN_RTR_REMOTE : CAN_RTR_DATA;
    tx_header.DLC      = dlc;
    tx_header.TransmitGlobalTime = ENABLE;

    uint32_t tx_mailbox;
    HAL_StatusTypeDef ret;

    /* Polling with timeout */
    uint32_t start = device_get_uptime_ms();
    while (1) {
        ret = HAL_CAN_AddTxMessage(h, &tx_header, (uint8_t *)data, &tx_mailbox);
        if (ret == HAL_OK) {
            ctx->stats.tx_success++;
            return CAN_OK;
        }
        if (timeout_ms == 0) {
            ctx->stats.tx_failed++;
            return CAN_ERR_NO_BUFFER;
        }
        if ((device_get_uptime_ms() - start) >= timeout_ms) {
            ctx->stats.tx_failed++;
            return CAN_ERR_TIMEOUT;
        }
    }
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

    if (HAL_CAN_Start(h) != HAL_OK) return CAN_ERR_HW;

    HAL_CAN_ActivateNotification(h, CAN_IT_RX_FIFO0_MSG_PENDING |
                                     CAN_IT_RX_FIFO1_MSG_PENDING |
                                     CAN_IT_ERROR |
                                     CAN_IT_BUSOFF |
                                     CAN_IT_LAST_ERROR_CODE |
                                     CAN_IT_ERROR_PASSIVE |
                                     CAN_IT_ERROR_WARNING);

    ctx->listening = 1;
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

    CAN_RxHeaderTypeDef rx_header;
    uint8_t rx_data[8];

    while (HAL_CAN_GetRxMessage(h, CAN_RX_FIFO0, &rx_header, rx_data) == HAL_OK) {
        can_frame_t frame;
        memset(&frame, 0, sizeof(frame));
        frame.id        = (rx_header.IDE == CAN_ID_EXT) ? rx_header.ExtId : rx_header.StdId;
        frame.ide       = (rx_header.IDE == CAN_ID_EXT) ? 1 : 0;
        frame.rtr       = (rx_header.RTR == CAN_RTR_REMOTE) ? 1 : 0;
        frame.dlc       = rx_header.DLC;
        frame.channel   = channel;
        frame.timestamp = rx_header.Timestamp != 0 ? rx_header.Timestamp : device_get_uptime_us();
        memcpy(frame.data, rx_data, frame.dlc > 8 ? 8 : frame.dlc);

        ctx->stats.rx_received++;

        if (ctx->rx_callback) {
            ctx->rx_callback(&frame);
        }
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

        /* Notify user via callback with an error frame */
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
        HAL_CAN_IRQHandler(h);
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
