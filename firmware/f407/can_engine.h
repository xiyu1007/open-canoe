/**
 * @file can_engine.h
 * @brief STM32F407VET6 dual bxCAN engine.
 *
 * Pinout (default):
 *   CAN1 RX → PD0, CAN1 TX → PD1
 *   CAN2 RX → PB12, CAN2 TX → PB13
 */

#ifndef CAN_ENGINE_H
#define CAN_ENGINE_H

#include <stdint.h>

#define CAN_RX_FIFO_SIZE 256
#define CAN_MAX_CHANNELS 2

typedef struct {
    uint32_t id;
    uint8_t  data[8];
    uint8_t  dlc;
    uint8_t  is_extended;
    uint8_t  is_remote;
    uint8_t  channel;  /* 0=CAN1, 1=CAN2 */
    uint32_t timestamp_us;
} can_msg_t;

void can_init(uint32_t bitrate);
void can_start(void);
void can_stop(void);
int  can_send(uint32_t id, int is_ext, const uint8_t *data, uint8_t dlc, int channel);
void can_rx_isr(const can_msg_t *msg);
void can_error_isr(uint32_t error_code);
int  can_poll_rx(can_msg_t *out);
int  can_poll_error(uint32_t *out);

#endif /* CAN_ENGINE_H */
