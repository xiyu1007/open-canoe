/**
 * @file can_engine.c
 * @brief STM32F103C8T6 bxCAN engine implementation.
 *
 * Targets: Blue Pill, any F103 board with PB8/PB9 CAN pins.
 * Build: arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -DSTM32F103xB
 */

#include "can_engine.h"
#include <string.h>
#include "stm32f1xx_hal.h"

/* ── Ring buffers ─────────────────────────────────────── */

static can_msg_t rx_ring[CAN_RX_FIFO_SIZE];
static volatile uint16_t rx_head = 0;
static uint16_t rx_tail = 0;

static uint32_t err_ring[32];
static volatile uint8_t err_head = 0;
static uint8_t err_tail = 0;

static CAN_HandleTypeDef hcan;

/* ── Init ──────────────────────────────────────────────── */

void can_init(uint32_t bitrate) {
    CAN_FilterTypeDef filter = {0};
    uint32_t prescaler;

    /* Clock: APB1=36MHz (HSE 8MHz→PLL 72MHz→APB1/2) */
    switch (bitrate) {
        case 100000:  prescaler = 36; break;  /* 36MHz/(36*10)=100k */
        case 125000:  prescaler = 18; break;  /* 36MHz/(18*16)=125k */
        case 250000:  prescaler = 9;  break;  /* 36MHz/(9*16)=250k  */
        case 500000:  prescaler = 9;  break;  /* 36MHz/(9*8)=500k   */
        case 1000000: prescaler = 4;  break;  /* 36MHz/(4*9)=1M     */
        default:      prescaler = 9;  break;
    }

    __HAL_RCC_CAN1_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    /* PB8=CAN_RX, PB9=CAN_TX */
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_8;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOB, &gpio);

    gpio.Pin = GPIO_PIN_9;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOB, &gpio);

    hcan.Instance = CAN1;
    hcan.Init.Prescaler = prescaler;
    hcan.Init.Mode = CAN_MODE_NORMAL;
    hcan.Init.SyncJumpWidth = CAN_SJW_1TQ;
    hcan.Init.TimeSeg1 = (bitrate == 100000) ? CAN_BS1_9TQ :
                         (bitrate == 500000) ? CAN_BS1_7TQ : CAN_BS1_8TQ;
    hcan.Init.TimeSeg2 = (bitrate == 100000) ? CAN_BS2_4TQ :
                         (bitrate == 1000000) ? CAN_BS2_4TQ : CAN_BS2_3TQ;
    hcan.Init.TimeTriggeredMode = DISABLE;
    hcan.Init.AutoBusOff = ENABLE;
    hcan.Init.AutoWakeUp = DISABLE;
    hcan.Init.AutoRetransmission = ENABLE;
    hcan.Init.ReceiveFifoLocked = DISABLE;
    hcan.Init.TransmitFifoPriority = DISABLE;
    HAL_CAN_Init(&hcan);

    /* Accept-all filter */
    filter.FilterIdHigh = 0x0000;
    filter.FilterIdLow = 0x0000;
    filter.FilterMaskIdHigh = 0x0000;
    filter.FilterMaskIdLow = 0x0000;
    filter.FilterFIFOAssignment = CAN_RX_FIFO0;
    filter.FilterBank = 0;
    filter.FilterMode = CAN_FILTERMODE_IDMASK;
    filter.FilterScale = CAN_FILTERSCALE_32BIT;
    filter.FilterActivation = ENABLE;
    HAL_CAN_ConfigFilter(&hcan, &filter);
}

void can_start(void) { HAL_CAN_Start(&hcan); }
void can_stop(void)  { HAL_CAN_Stop(&hcan); }

/* ── Send ──────────────────────────────────────────────── */

int can_send(uint32_t id, int is_ext, const uint8_t *data, uint8_t dlc) {
    CAN_TxHeaderTypeDef hdr = {0};
    uint32_t mb;

    hdr.IDE   = is_ext ? CAN_ID_EXT : CAN_ID_STD;
    hdr.StdId = is_ext ? 0 : id;
    hdr.ExtId = is_ext ? id : 0;
    hdr.RTR   = CAN_RTR_DATA;
    hdr.DLC   = dlc > 8 ? 8 : dlc;

    return HAL_CAN_AddTxMessage(&hcan, &hdr, (uint8_t *)data, &mb);
}

/* ── ISR handlers ──────────────────────────────────────── */

void can_rx_isr(const can_msg_t *msg) {
    uint16_t next = (rx_head + 1) % CAN_RX_FIFO_SIZE;
    if (next == rx_tail) return; /* overflow */
    rx_ring[rx_head] = *msg;
    rx_head = next;
}

void can_error_isr(uint32_t code) {
    uint8_t next = (err_head + 1) % 32;
    if (next == err_tail) return;
    err_ring[err_head] = code;
    err_head = next;
}

/* ── Poll ──────────────────────────────────────────────── */

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
