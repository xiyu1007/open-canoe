/**
 * @file main.c
 * @brief STM32F103C8T6 firmware — CAN-to-USB bridge.
 *
 * Main loop:
 *   1. Poll USB CDC for host commands → dispatch
 *   2. Poll CAN RX ring → encode + send to host
 *   3. Poll CAN errors → send error frames to host
 */

#include "can_engine.h"
#include "usb_cdc.h"
#include "protocol.h"
#include "stm32f1xx_hal.h"

#define DEFAULT_BITRATE 500000

/* ── Transport write callback ─────────────────────────── */

static void write_byte(uint8_t b) { usb_cdc_write_byte(b); }

/* ── Capabilities response ────────────────────────────── */

static void send_capabilities(void) {
    uint8_t cap[24] = {0};
    cap[0] = PROTO_VER;
    cap[1] = CAN_MAX_CHANNELS;
    cap[2] = 0; /* CAN FD: not supported */
    cap[3] = 12; /* ADC bits */
    /* adc_max_khz at cap[4..7] = 1000 (1 Msps) */
    cap[4] = 0xE8; cap[5] = 0x03; /* 1000 LE */
    const char *name = "open-canoe F103";
    memcpy(cap + 8, name, __builtin_strlen(name));
    proto_send_frame(CMD_CAPABILITIES_RESP, cap, sizeof(cap), write_byte);
}

/* ── CAN RX forward ───────────────────────────────────── */

static void forward_can_message(void) {
    can_msg_t msg;
    if (!can_poll_rx(&msg)) return;

    uint8_t pkt[4 + 1 + 1 + 8 + 4] = {0}; /* id|flags|dlc|data|ts */
    uint16_t pos = 0;
    pkt[pos++] = msg.id & 0xFF;
    pkt[pos++] = (msg.id >> 8) & 0xFF;
    pkt[pos++] = (msg.id >> 16) & 0xFF;
    pkt[pos++] = (msg.id >> 24) & 0xFF;
    pkt[pos++] = (msg.is_extended ? CAN_FLAG_EXTENDED : 0) |
                 (msg.is_remote ? CAN_FLAG_REMOTE : 0);
    pkt[pos++] = msg.dlc;
    memcpy(pkt + pos, msg.data, msg.dlc > 8 ? 8 : msg.dlc);
    pos += 8;
    pkt[pos++] = msg.timestamp_us & 0xFF;
    pkt[pos++] = (msg.timestamp_us >> 8) & 0xFF;
    pkt[pos++] = (msg.timestamp_us >> 16) & 0xFF;
    pkt[pos++] = (msg.timestamp_us >> 24) & 0xFF;

    proto_send_frame(CMD_CAN_MESSAGE_RX, pkt, sizeof(pkt), write_byte);
}

/* ── Host command dispatch ────────────────────────────── */

static void dispatch(uint8_t cmd, const uint8_t *payload, uint16_t len) {
    switch (cmd) {
    case CMD_CAPABILITIES_REQ:
        send_capabilities();
        break;
    case CMD_CAN_OPEN:
        can_start();
        break;
    case CMD_CAN_CLOSE:
        can_stop();
        break;
    case CMD_CAN_SEND:
        if (len >= 10) {
            uint32_t id = payload[0] | ((uint32_t)payload[1] << 8) |
                          ((uint32_t)payload[2] << 16) | ((uint32_t)payload[3] << 24);
            uint8_t flags = payload[4];
            uint8_t dlc   = payload[5];
            can_send(id, flags & CAN_FLAG_EXTENDED, payload + 6, dlc);
        }
        break;
    case CMD_CAN_SET_BITRATE:
        if (len >= 4) {
            uint32_t br = payload[0] | ((uint32_t)payload[1] << 8) |
                          ((uint32_t)payload[2] << 16) | ((uint32_t)payload[3] << 24);
            can_stop();
            can_init(br);
            can_start();
        }
        break;
    case CMD_RESET:
        NVIC_SystemReset();
        break;
    }
}

/* ── Entry ─────────────────────────────────────────────── */

int main(void) {
    HAL_Init();
    SystemCoreClockUpdate();

    usb_cdc_init();
    can_init(DEFAULT_BITRATE);

    for (;;) {
        /* Process host commands */
        uint8_t c;
        while (usb_cdc_read_byte(&c)) {
            uint8_t cmd;
            const uint8_t *pl;
            uint16_t plen;
            if (proto_feed_byte(c, &cmd, &pl, &plen))
                dispatch(cmd, pl, plen);
        }

        /* Forward CAN messages */
        forward_can_message();

        /* Forward CAN errors */
        uint32_t err;
        if (can_poll_error(&err)) {
            uint8_t eb[4];
            eb[0] = err & 0xFF;
            eb[1] = (err >> 8) & 0xFF;
            eb[2] = (err >> 16) & 0xFF;
            eb[3] = (err >> 24) & 0xFF;
            proto_send_frame(CMD_CAN_ERROR, eb, 4, write_byte);
        }
    }
}
