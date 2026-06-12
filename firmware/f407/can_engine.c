/**
 * @file can_engine.c
 * @brief STM32F407VET6 dual bxCAN engine.
 *
 * Key differences from F103:
 *   - 2 CAN peripherals (CAN1 @ PD0/PD1, CAN2 @ PB12/PB13)
 *   - APB1=42MHz (168MHz/4) vs F103's 36MHz
 *   - 512KB Flash, 128KB SRAM
 */

#include "can_engine.h"
#include <string.h>
#include "stm32f4xx_hal.h"

/* ── Ring buffers ─────────────────────────────────────── */

static can_msg_t rx_ring[CAN_RX_FIFO_SIZE];
static volatile uint16_t rx_head = 0;
static uint16_t rx_tail = 0;

static uint32_t err_ring[32];
static volatile uint8_t err_head = 0;
static uint8_t err_tail = 0;

static CAN_HandleTypeDef hcan1, hcan2;

/* ── Init ──────────────────────────────────────────────── */

void can_init(uint32_t bitrate) {
    CAN_FilterTypeDef filter = {0};

    /* APB1 = 42 MHz (168 MHz / 4) */
    uint32_t prescaler;
    switch (bitrate) {
        case 100000:  prescaler = 42; break; /* 42MHz/(42*10)=100k  */
        case 125000:  prescaler = 21; break; /* 42MHz/(21*16)=125k  */
        case 250000:  prescaler = 10; break; /* 42MHz/(10*16.8)~250k*/
        case 500000:  prescaler = 7;  break; /* 42MHz/(7*12)=500k   */
        case 1000000: prescaler = 7;  break; /* 42MHz/(7*6)=1M      */
        default:      prescaler = 7;  break;
    }

    __HAL_RCC_CAN1_CLK_ENABLE();
    __HAL_RCC_CAN2_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    /* CAN1: PD0=RX, PD1=TX */
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_0;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_PULLUP;
    gpio.Alternate = GPIO_AF9_CAN1;
    HAL_GPIO_Init(GPIOD, &gpio);

    gpio.Pin = GPIO_PIN_1;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Alternate = GPIO_AF9_CAN1;
    HAL_GPIO_Init(GPIOD, &gpio);

    /* CAN2: PB12=RX, PB13=TX */
    gpio.Pin = GPIO_PIN_12;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_PULLUP;
    gpio.Alternate = GPIO_AF9_CAN2;
    HAL_GPIO_Init(GPIOB, &gpio);

    gpio.Pin = GPIO_PIN_13;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Alternate = GPIO_AF9_CAN2;
    HAL_GPIO_Init(GPIOB, &gpio);

    /* Configure both CAN peripherals identically */
    CAN_HandleTypeDef *cans[] = {&hcan1, &hcan2, NULL};
    CAN_TypeDef *inst[] = {CAN1, CAN2, NULL};
    for (int i = 0; cans[i]; i++) {
        cans[i]->Instance = inst[i];
        cans[i]->Init.Prescaler = prescaler;
        cans[i]->Init.Mode = CAN_MODE_NORMAL;
        cans[i]->Init.SyncJumpWidth = CAN_SJW_1TQ;
        cans[i]->Init.TimeSeg1 = CAN_BS1_11TQ;
        cans[i]->Init.TimeSeg2 = CAN_BS2_2TQ;
        cans[i]->Init.TimeTriggeredMode = DISABLE;
        cans[i]->Init.AutoBusOff = ENABLE;
        cans[i]->Init.AutoWakeUp = DISABLE;
        cans[i]->Init.AutoRetransmission = ENABLE;
        cans[i]->Init.ReceiveFifoLocked = DISABLE;
        cans[i]->Init.TransmitFifoPriority = DISABLE;
        HAL_CAN_Init(cans[i]);
    }

    /* Accept-all filters (split across CAN1 and CAN2) */
    filter.FilterIdHigh = 0x0000;
    filter.FilterIdLow = 0x0000;
    filter.FilterMaskIdHigh = 0x0000;
    filter.FilterMaskIdLow = 0x0000;
    filter.FilterMode = CAN_FILTERMODE_IDMASK;
    filter.FilterScale = CAN_FILTERSCALE_32BIT;
    filter.FilterActivation = ENABLE;
    filter.FilterBank = 0;
    filter.FilterFIFOAssignment = CAN_RX_FIFO0;
    HAL_CAN_ConfigFilter(&hcan1, &filter);
    filter.FilterBank = 14;
    filter.FilterFIFOAssignment = CAN_RX_FIFO0;
    HAL_CAN_ConfigFilter(&hcan2, &filter);
}

void can_start(void) {
    HAL_CAN_Start(&hcan1);
    HAL_CAN_Start(&hcan2);
}

void can_stop(void) {
    HAL_CAN_Stop(&hcan1);
    HAL_CAN_Stop(&hcan2);
}

int can_send(uint32_t id, int is_ext, const uint8_t *data, uint8_t dlc, int ch) {
    CAN_HandleTypeDef *h = (ch == 1) ? &hcan2 : &hcan1;
    CAN_TxHeaderTypeDef hdr = {0};
    uint32_t mb;
    hdr.IDE   = is_ext ? CAN_ID_EXT : CAN_ID_STD;
    hdr.StdId = is_ext ? 0 : id;
    hdr.ExtId = is_ext ? id : 0;
    hdr.RTR   = CAN_RTR_DATA;
    hdr.DLC   = dlc > 8 ? 8 : dlc;
    return HAL_CAN_AddTxMessage(h, &hdr, (uint8_t *)data, &mb);
}

/* ── ISR / Poll (same lock-free SPSC ring as F103) ─────── */

void can_rx_isr(const can_msg_t *msg) {
    uint16_t next = (rx_head + 1) % CAN_RX_FIFO_SIZE;
    if (next == rx_tail) return;
    rx_ring[rx_head] = *msg;
    rx_head = next;
}

void can_error_isr(uint32_t code) {
    uint8_t next = (err_head + 1) % 32;
    if (next == err_tail) return;
    err_ring[err_head] = code;
    err_head = next;
}

int can_poll_rx(can_msg_t *out) {
    if (rx_tail == rx_head) return 0;
    *out = rx_ring[rx_tail];
    rx_tail = (rx_tail + 1) % CAN_RX_FIFO_SIZE;
    return 1;
}

int can_poll_error(uint32_t *out) {
    if (err_tail == err_head) return 0;
    *out = err_ring[err_tail];
    err_tail = (err_tail + 1) % 32;
    return 1;
}
