/**
 * @file protocol.h
 * @brief Binary framed protocol shared between firmware and host.
 *
 * Wire format: STX(0xAA) | CMD(1B) | LEN(2B LE) | PAYLOAD(0..255B) | CRC16(2B LE) | ETX(0x55)
 * CRC-16/XMODEM (poly 0x1021).
 *
 * Keep in sync with canoe/core/protocol.py.
 */

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>

#define PROTO_STX  0xAA
#define PROTO_ETX  0x55
#define PROTO_VER  0x01

/* ── Commands ─────────────────────────────────────────── */
enum {
    /* Host → Firmware */
    CMD_CAPABILITIES_REQ  = 0x01,
    CMD_CAN_OPEN          = 0x10,
    CMD_CAN_CLOSE         = 0x11,
    CMD_CAN_SEND          = 0x12,
    CMD_CAN_SET_FILTER    = 0x13,
    CMD_CAN_SET_BITRATE   = 0x14,
    CMD_WAVE_START        = 0x20,
    CMD_WAVE_STOP         = 0x21,
    CMD_RESET             = 0x7F,

    /* Firmware → Host */
    CMD_CAPABILITIES_RESP = 0x81,
    CMD_CAN_MESSAGE_RX    = 0x90,
    CMD_CAN_ERROR         = 0x91,
    CMD_CAN_BUS_STATUS    = 0x92,
    CMD_WAVE_SAMPLE       = 0xA0,
    CMD_WAVE_DONE         = 0xA1,
    CMD_LOG_MESSAGE       = 0xF0,
};

/* ── CAN message wire format (CMD_CAN_MESSAGE_RX) ────── */
/* id(4B LE) | flags(1B) | dlc(1B) | data(8B) | timestamp_us(4B LE) */
#define CAN_FLAG_EXTENDED  0x01
#define CAN_FLAG_REMOTE    0x02

/* ── Capabilities response ────────────────────────────── */
/* version(1B) | can_channels(1B) | can_fd(1B) | adc_bits(1B) | adc_max_khz(4B LE) | name(16B) */

/* ── Public API ───────────────────────────────────────── */

uint16_t proto_crc16(const uint8_t *data, uint16_t len);

/**
 * Encode and send a frame over the transport.
 * Caller must provide a _write_fn(uint8_t byte) to push bytes out.
 */
void proto_send_frame(uint8_t cmd, const uint8_t *payload, uint16_t len,
                      void (*write_fn)(uint8_t));

/**
 * Feed one byte into the protocol decoder.
 * Returns 1 when a complete, valid frame has been received.
 * On return, *cmd, *payload_* and *payload_len are set.
 */
int  proto_feed_byte(uint8_t byte, uint8_t *cmd,
                     const uint8_t **payload, uint16_t *payload_len);

void proto_reset(void);

#endif /* PROTOCOL_H */
