/**
 * @file main.c
 * @brief STM32F407VET6 firmware — dual CAN-to-USB bridge.
 *
 * Identical to F103 main loop, but supports 2 CAN channels.
 * Compile: arm-none-eabi-gcc -mcpu=cortex-m4 -DSTM32F407xx
 */

#include "can_engine.h"
#include "../f103/usb_cdc.h"   /* same CDC interface */
#include "../common/protocol.h"
#include "stm32f4xx_hal.h"

#define DEFAULT_BITRATE 500000

static void write_byte(uint8_t b) { usb_cdc_write_byte(b); }

static void send_capabilities(void) {
    uint8_t cap[24] = {0};
    cap[0] = PROTO_VER;
    cap[1] = CAN_MAX_CHANNELS;  /* 2 */
    cap[2] = 0;
    cap[3] = 12;
    cap[4] = 0xE8; cap[5] = 0x03;
    const char *name = "open-canoe F407";
    memcpy(cap + 8, name, __builtin_strlen(name));
    proto_send_frame(CMD_CAPABILITIES_RESP, cap, sizeof(cap), write_byte);
}

static void forward_can(void) {
    can_msg_t msg;
    if (!can_poll_rx(&msg)) return;

    uint8_t pkt[4+1+1+8+4] = {0};
    uint16_t pos = 0;
    pkt[pos++] = msg.id & 0xFF;
    pkt[pos++] = (msg.id >> 8) & 0xFF;
    pkt[pos++] = (msg.id >> 16) & 0xFF;
    pkt[pos++] = (msg.id >> 24) & 0xFF;
    pkt[pos++] = (msg.is_extended ? 0x01 : 0) | (msg.is_remote ? 0x02 : 0);
    pkt[pos++] = msg.dlc;
    memcpy(pkt + pos, msg.data, msg.dlc > 8 ? 8 : msg.dlc);
    pos += 8;
    pkt[pos++] = msg.timestamp_us & 0xFF;
    pkt[pos++] = (msg.timestamp_us >> 8) & 0xFF;
    pkt[pos++] = (msg.timestamp_us >> 16) & 0xFF;
    pkt[pos++] = (msg.timestamp_us >> 24) & 0xFF;
    proto_send_frame(CMD_CAN_MESSAGE_RX, pkt, sizeof(pkt), write_byte);
}

static void dispatch(uint8_t cmd, const uint8_t *p, uint16_t len) {
    switch (cmd) {
    case CMD_CAPABILITIES_REQ: send_capabilities(); break;
    case CMD_CAN_OPEN:         can_start(); break;
    case CMD_CAN_CLOSE:        can_stop(); break;
    case CMD_CAN_SEND:
        if (len >= 10) {
            uint32_t id = p[0]|(p[1]<<8)|(p[2]<<16)|(p[3]<<24);
            can_send(id, p[4]&1, p+6, p[5], 0);
        }
        break;
    case CMD_RESET: NVIC_SystemReset(); break;
    }
}

int main(void) {
    HAL_Init();
    SystemCoreClockUpdate();
    usb_cdc_init();
    can_init(DEFAULT_BITRATE);

    for (;;) {
        uint8_t c;
        while (usb_cdc_read_byte(&c)) {
            uint8_t cmd; const uint8_t *pl; uint16_t plen;
            if (proto_feed_byte(c, &cmd, &pl, &plen)) dispatch(cmd, pl, plen);
        }
        forward_can();
        uint32_t err;
        if (can_poll_error(&err)) {
            uint8_t eb[4] = {err, err>>8, err>>16, err>>24};
            proto_send_frame(CMD_CAN_ERROR, eb, 4, write_byte);
        }
    }
}
