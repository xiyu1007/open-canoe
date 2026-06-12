/**
 * @file can_engine.h
 * @brief STM32F103C8T6 bxCAN engine — single channel.
 *
 * Pinout (default):
 *   CAN1 RX → PB8
 *   CAN1 TX → PB9
 */

#ifndef CAN_ENGINE_H
#define CAN_ENGINE_H

#include <stdint.h>

#define CAN_RX_FIFO_SIZE 256
#define CAN_MAX_CHANNELS 1

/* ── Public types ─────────────────────────────────────── */

typedef struct {
    uint32_t id;
    uint8_t  data[8];
    uint8_t  dlc;
    uint8_t  is_extended;
    uint8_t  is_remote;
    uint32_t timestamp_us;
} can_msg_t;

/* ── Public API ───────────────────────────────────────── */

void can_init(uint32_t bitrate);
void can_start(void);
void can_stop(void);
int  can_send(uint32_t id, int is_ext, const uint8_t *data, uint8_t dlc);

/** ISR-call: push received frame into ring buffer. */
void can_rx_isr(const can_msg_t *msg);

/** ISR-call: record error event. */
void can_error_isr(uint32_t error_code);

/** Main-loop poll: pop one received message (1=available, 0=empty). */
int  can_poll_rx(can_msg_t *out);

/** Main-loop poll: pop one error event (1=available, 0=empty). */
int  can_poll_error(uint32_t *out);

#endif /* CAN_ENGINE_H */
