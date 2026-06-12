/**
 * @file protocol.c
 * @brief Protocol encoder/decoder implementation.
 */

#include "protocol.h"
#include <string.h>

/* ── CRC-16/XMODEM lookup table ──────────────────────── */

static uint16_t crc_table[256];
static int crc_table_ready = 0;

static void crc_make_table(void) {
    for (int i = 0; i < 256; i++) {
        uint16_t crc = (uint16_t)i << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
        crc_table[i] = crc;
    }
    crc_table_ready = 1;
}

uint16_t proto_crc16(const uint8_t *data, uint16_t len) {
    if (!crc_table_ready) crc_make_table();
    uint16_t crc = 0;
    for (uint16_t i = 0; i < len; i++)
        crc = (crc << 8) ^ crc_table[((crc >> 8) ^ data[i]) & 0xFF];
    return crc;
}

/* ── Send ─────────────────────────────────────────────── */

void proto_send_frame(uint8_t cmd, const uint8_t *payload, uint16_t len,
                      void (*write_fn)(uint8_t)) {
    write_fn(PROTO_STX);
    write_fn(cmd);
    write_fn(len & 0xFF);
    write_fn((len >> 8) & 0xFF);

    /* CMD + LEN(2) + PAYLOAD for CRC */
    uint8_t  crc_buf[3 + 256]; /* max payload */
    crc_buf[0] = cmd;
    crc_buf[1] = len & 0xFF;
    crc_buf[2] = (len >> 8) & 0xFF;
    if (payload && len > 0) memcpy(crc_buf + 3, payload, len);
    uint16_t crc = proto_crc16(crc_buf, 3 + len);

    if (payload && len > 0)
        for (uint16_t i = 0; i < len; i++) write_fn(payload[i]);

    write_fn(crc & 0xFF);
    write_fn((crc >> 8) & 0xFF);
    write_fn(PROTO_ETX);
}

/* ── Receive state machine ────────────────────────────── */

#define RX_BUF_SIZE 512

static uint8_t  rx_buf[RX_BUF_SIZE];
static uint16_t rx_pos = 0;

void proto_reset(void) { rx_pos = 0; }

int proto_feed_byte(uint8_t byte, uint8_t *cmd,
                    const uint8_t **payload, uint16_t *payload_len) {
    if (rx_pos >= RX_BUF_SIZE) { rx_pos = 0; return 0; }
    rx_buf[rx_pos++] = byte;

    /* Need at least: STX + CMD + LEN(2) + CRC(2) + ETX = 7 bytes */
    if (rx_pos < 7) return 0;

    /* Find STX */
    uint16_t start = 0;
    while (start < rx_pos && rx_buf[start] != PROTO_STX) start++;
    if (start > 0) {
        memmove(rx_buf, rx_buf + start, rx_pos - start);
        rx_pos -= start;
        if (rx_pos < 7) return 0;
    }

    uint16_t plen = rx_buf[2] | ((uint16_t)rx_buf[3] << 8);
    uint16_t frame_len = 7 + plen;
    if (rx_pos < frame_len) return 0; /* incomplete */

    if (rx_buf[frame_len - 1] != PROTO_ETX) {
        memmove(rx_buf, rx_buf + 1, rx_pos - 1);
        rx_pos--;
        return 0;
    }

    uint16_t crc_rx = rx_buf[4 + plen + 1] | ((uint16_t)rx_buf[4 + plen + 2] << 8);
    if (proto_crc16(rx_buf + 1, 3 + plen) != crc_rx) {
        memmove(rx_buf, rx_buf + 1, rx_pos - 1);
        rx_pos--;
        return 0;
    }

    *cmd         = rx_buf[1];
    *payload     = plen > 0 ? rx_buf + 4 : NULL;
    *payload_len = plen;

    memmove(rx_buf, rx_buf + frame_len, rx_pos - frame_len);
    rx_pos -= frame_len;
    return 1;
}
