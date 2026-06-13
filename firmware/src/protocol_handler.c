/**
 * @file    protocol_handler.c
 * @brief   Protocol encode/decode engine. Calls abstract HAL APIs only.
 * @note    This file has NO MCU-specific includes — it works with any HAL backend.
 */

#include "protocol.h"
#include "can_api.h"
#include "adc_api.h"
#include "comm_api.h"
#include "device_api.h"
#include <string.h>

/* Forward declarations */
extern void protocol_send_can_frame(const can_frame_t *frame);

/*============================================================================
 * Internal State
 *============================================================================*/

static uint16_t g_seq_counter = 0;

/* Wait buffer for partial frame reassembly */
static uint8_t  g_rx_buf[PROTOCOL_FRAME_TOTAL_MAX];
static uint16_t g_rx_buf_pos = 0;
static uint16_t g_rx_expected_len = 0;

/*============================================================================
 * CRC16 (CRC-CCITT, polynomial 0x1021)
 *============================================================================*/

static uint16_t crc16_update(uint16_t crc, uint8_t byte)
{
    crc ^= (uint16_t)byte << 8;
    for (uint8_t i = 0; i < 8; i++) {
        if (crc & 0x8000) {
            crc = (crc << 1) ^ 0x1021;
        } else {
            crc <<= 1;
        }
    }
    return crc;
}

static uint16_t crc16_compute(const uint8_t *data, uint16_t length)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; i++) {
        crc = crc16_update(crc, data[i]);
    }
    return crc;
}

/*============================================================================
 * Frame Assembly Helpers
 *============================================================================*/

/**
 * @brief Write a protocol frame into the output buffer.
 * @param cmd       Command/response code
 * @param data      Payload data (can be NULL if data_len == 0)
 * @param data_len  Payload length in bytes
 * @param out_buf   Output buffer (caller-allocated)
 * @param out_len   Output: total frame length written
 * @return 0 on success, -1 if data_len exceeds max
 */
static int proto_build_frame(uint8_t cmd, const uint8_t *data,
                             uint16_t data_len, uint8_t *out_buf,
                             uint16_t *out_len)
{
    if (data_len > PROTOCOL_FRAME_DATA_MAX) return -1;

    uint16_t total_len = PROTO_CALC_LENGTH(data_len);
    uint16_t seq = g_seq_counter++;

    /* Header */
    out_buf[0] = PROTOCOL_MAGIC_HEADER;
    out_buf[1] = (uint8_t)(total_len & 0xFF);
    out_buf[2] = (uint8_t)((total_len >> 8) & 0xFF);
    out_buf[3] = cmd;
    out_buf[4] = (uint8_t)(seq & 0xFF);
    out_buf[5] = (uint8_t)((seq >> 8) & 0xFF);

    /* Data */
    if (data_len > 0 && data != NULL) {
        memcpy(&out_buf[PROTOCOL_FRAME_HEADER_SIZE], data, data_len);
    }

    /* CRC16 over header + data */
    uint16_t crc = crc16_compute(out_buf, PROTOCOL_FRAME_HEADER_SIZE + data_len);
    uint16_t crc_offset = PROTOCOL_FRAME_HEADER_SIZE + data_len;
    out_buf[crc_offset]     = (uint8_t)(crc & 0xFF);
    out_buf[crc_offset + 1] = (uint8_t)((crc >> 8) & 0xFF);

    /* End magic */
    out_buf[crc_offset + 2] = PROTOCOL_END_MAGIC;

    *out_len = total_len;
    return 0;
}

/**
 * @brief Send a response frame (no data payload).
 */
static int proto_send_simple(uint8_t cmd)
{
    uint8_t buf[PROTOCOL_FRAME_TOTAL_MAX];
    uint16_t len;
    if (proto_build_frame(cmd, NULL, 0, buf, &len) != 0) return -1;
    return (comm_send(buf, len, 100) == COMM_OK) ? 0 : -1;
}

/**
 * @brief Send a response with payload.
 */
static int proto_send_data(uint8_t cmd, const uint8_t *data, uint16_t data_len)
{
    uint8_t buf[PROTOCOL_FRAME_TOTAL_MAX];
    uint16_t len;
    if (proto_build_frame(cmd, data, data_len, buf, &len) != 0) return -1;
    return (comm_send(buf, len, 100) == COMM_OK) ? 0 : -1;
}

/*============================================================================
 * Command Handlers
 *============================================================================*/

static void handle_get_info(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    device_info_t info;
    device_get_info(&info);

    device_info_resp_t resp;
    memset(&resp, 0, sizeof(resp));
    resp.fw_major   = info.fw_major;
    resp.fw_minor   = info.fw_minor;
    resp.fw_patch   = info.fw_patch;
    resp.protocol_version = (uint16_t)((PROTOCOL_VERSION_MAJOR << 8) | PROTOCOL_VERSION_MINOR);
    resp.device_serial = info.device_serial;
    strncpy(resp.mcu_model, info.mcu_model, sizeof(resp.mcu_model) - 1);
    strncpy(resp.fw_description, info.fw_description, sizeof(resp.fw_description) - 1);

    proto_send_data(MSG_INFO_RESPONSE, (const uint8_t *)&resp, sizeof(resp));
}

static void handle_get_capabilities(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    device_capabilities_t caps;
    device_get_capabilities(&caps);

    capabilities_resp_t resp;
    memset(&resp, 0, sizeof(resp));
    resp.capability_bits    = caps.capability_bits;
    resp.can_channel_count  = caps.can_channel_count;
    resp.max_adc_sample_rate = caps.max_adc_sample_rate;
    resp.adc_resolution     = caps.adc_resolution_bits;
    resp.max_can_baudrate   = caps.max_can_baudrate_kbps;

    proto_send_data(MSG_CAPABILITIES_RESP, (const uint8_t *)&resp, sizeof(resp));
}

static void handle_get_status(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    status_resp_t resp;
    memset(&resp, 0, sizeof(resp));
    resp.can_listening  = can_is_initialized(0) ? 1 : 0;
    resp.comm_interface = (uint8_t)comm_get_current_interface();
    resp.uptime_ms      = device_get_uptime_ms();

    /* Check CAN channels active */
    uint8_t ch_active = 0;
    for (uint8_t ch = 0; ch < can_get_channel_count(); ch++) {
        if (can_is_initialized(ch)) ch_active |= (1U << ch);
    }
    resp.can_channels_active = ch_active;

    /* Check ADC status */
    uint8_t is_sampling;
    uint32_t sample_rate;
    uint8_t resolution;
    if (adc_get_status(&is_sampling, &sample_rate, &resolution) == ADC_OK) {
        resp.adc_sampling = is_sampling;
    }

    proto_send_data(MSG_STATUS_RESPONSE, (const uint8_t *)&resp, sizeof(resp));
}

static void handle_get_adc_status(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    uint8_t is_sampling = 0;
    uint32_t sample_rate = 0;
    uint8_t resolution = 0;
    uint8_t available = adc_is_available();

    if (available) {
        adc_get_status(&is_sampling, &sample_rate, &resolution);
    }

    /* Simple ADC status response: [available][is_sampling][resolution][sample_rate(4)] */
    uint8_t resp[7];
    resp[0] = available;
    resp[1] = is_sampling;
    resp[2] = resolution;
    resp[3] = (uint8_t)(sample_rate & 0xFF);
    resp[4] = (uint8_t)((sample_rate >> 8) & 0xFF);
    resp[5] = (uint8_t)((sample_rate >> 16) & 0xFF);
    resp[6] = (uint8_t)((sample_rate >> 24) & 0xFF);

    proto_send_data(MSG_ADC_STATUS_RESP, resp, sizeof(resp));
}

static void handle_can_set_baudrate(const uint8_t *data, uint16_t data_len)
{
    if (data_len < sizeof(can_set_baudrate_t)) {
        proto_send_simple(MSG_NACK);
        return;
    }

    const can_set_baudrate_t *req = (const can_set_baudrate_t *)data;
    can_status_t ret;

    /* Always use can_init (SPL-style direct register writes).
     * can_set_baudrate uses HAL_CAN_Init which is unreliable on F103.
     * Deinit first if previously initialized to ensure clean state. */
    if (can_is_initialized(req->channel)) {
        can_deinit(req->channel);
    }
    {
        can_config_t cfg;
        cfg.channel  = req->channel;
        cfg.baudrate = req->baudrate;
        cfg.mode     = CAN_MODE_NORMAL;
        ret = can_init(req->channel, &cfg);
    }

    ack_resp_t ack;
    ack.ack_cmd    = CMD_CAN_SET_BAUDRATE;
    ack.error_code = (ret == CAN_OK) ? ERR_NONE : ERR_HARDWARE_FAULT;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_can_set_mode(const uint8_t *data, uint16_t data_len)
{
    if (data_len < sizeof(can_set_mode_t)) {
        proto_send_simple(MSG_NACK);
        return;
    }

    const can_set_mode_t *req = (const can_set_mode_t *)data;
    can_status_t ret = can_set_mode(req->channel, req->mode);

    ack_resp_t ack;
    ack.ack_cmd    = CMD_CAN_SET_MODE;
    ack.error_code = (ret == CAN_OK) ? ERR_NONE : ERR_INVALID_PARAM;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_can_set_filter(const uint8_t *data, uint16_t data_len)
{
    if (data_len < sizeof(can_set_filter_t)) {
        proto_send_simple(MSG_NACK);
        return;
    }

    const can_set_filter_t *req = (const can_set_filter_t *)data;
    can_status_t ret = can_set_filter(req->channel, req->filter_index,
                                       req->filter_mode, req->filter_scale,
                                       req->id_high, req->id_low,
                                       req->mask_high, req->mask_low);

    ack_resp_t ack;
    ack.ack_cmd    = CMD_CAN_SET_FILTER;
    ack.error_code = (ret == CAN_OK) ? ERR_NONE : ERR_INVALID_PARAM;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_adc_set_sampling(const uint8_t *data, uint16_t data_len)
{
    if (data_len < sizeof(adc_set_sampling_t)) {
        proto_send_simple(MSG_NACK);
        return;
    }

    const adc_set_sampling_t *req = (const adc_set_sampling_t *)data;

    if (!adc_is_available()) {
        ack_resp_t ack;
        ack.ack_cmd    = CMD_ADC_SET_SAMPLING;
        ack.error_code = ERR_ADC_NOT_AVAILABLE;
        proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
        return;
    }

    adc_config_t config;
    config.sample_rate = req->sample_rate;
    config.resolution  = req->resolution;
    config.channel     = req->channel;
    config.source      = ADC_SOURCE_ADC;

    adc_status_t ret = adc_init(&config);

    ack_resp_t ack;
    ack.ack_cmd    = CMD_ADC_SET_SAMPLING;
    ack.error_code = (ret == ADC_OK) ? ERR_NONE : ERR_INVALID_PARAM;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_comm_set_interface(const uint8_t *data, uint16_t data_len)
{
    if (data_len < sizeof(comm_set_interface_t)) {
        proto_send_simple(MSG_NACK);
        return;
    }

    const comm_set_interface_t *req = (const comm_set_interface_t *)data;
    comm_interface_t target = (req->interface == COMM_IF_USB_CDC) ?
                            COMM_IF_USB_CDC : COMM_IF_USART;

    comm_status_t ret = comm_switch_interface(target, 115200);

    ack_resp_t ack;
    ack.ack_cmd    = CMD_COMM_SET_INTERFACE;
    ack.error_code = (ret == COMM_OK) ? ERR_NONE : ERR_COMM_TX_FAILED;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_can_start_listen(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    can_status_t ret = can_start_listen(0);

    ack_resp_t ack;
    ack.ack_cmd    = CMD_CAN_START_LISTEN;
    ack.error_code = (ret == CAN_OK) ? ERR_NONE : ERR_HARDWARE_FAULT;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_can_stop_listen(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    can_status_t ret = can_stop_listen(0);

    ack_resp_t ack;
    ack.ack_cmd    = CMD_CAN_STOP_LISTEN;
    ack.error_code = (ret == CAN_OK) ? ERR_NONE : ERR_HARDWARE_FAULT;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_adc_start_sample(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    if (!adc_is_available()) {
        ack_resp_t ack;
        ack.ack_cmd    = CMD_ADC_START_SAMPLE;
        ack.error_code = ERR_ADC_NOT_AVAILABLE;
        proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
        return;
    }

    adc_status_t ret = adc_start_sampling();

    ack_resp_t ack;
    ack.ack_cmd    = CMD_ADC_START_SAMPLE;
    ack.error_code = (ret == ADC_OK) ? ERR_NONE : ERR_HARDWARE_FAULT;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_adc_stop_sample(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    adc_status_t ret = adc_stop_sampling();

    ack_resp_t ack;
    ack.ack_cmd    = CMD_ADC_STOP_SAMPLE;
    ack.error_code = (ret == ADC_OK) ? ERR_NONE : ERR_HARDWARE_FAULT;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}

static void handle_can_send_frame(const uint8_t *data, uint16_t data_len)
{
    if (data_len < sizeof(can_send_frame_t)) {
        proto_send_simple(MSG_NACK);
        return;
    }

    const can_send_frame_t *req = (const can_send_frame_t *)data;
    uint8_t ide = req->flags & 0x01;
    uint8_t rtr = (req->flags >> 1) & 0x01;

    /* Auto-initialize CAN if not yet configured */
    if (!can_is_initialized(req->channel)) {
        can_config_t cfg;
        cfg.channel  = req->channel;
        cfg.baudrate = 500000;
        cfg.mode     = CAN_MODE_NORMAL;
        if (can_init(req->channel, &cfg) != CAN_OK) {
            ack_resp_t ack;
            ack.ack_cmd    = CMD_CAN_SEND_FRAME;
            ack.error_code = ERR_CAN_TX_FAILED;
            proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
            return;
        }
        can_start_listen(req->channel);
    }

    /* Silence CAN interrupts during the send+poll busy-wait.
     * Even with IER=0 from can_start_listen, explicitly writing 0 here
     * clears any residual interrupt state in the CAN peripheral. */
    volatile uint32_t *CAN1_IER = (volatile uint32_t *)0x40006414;
    volatile uint32_t *CAN1_ESR = (volatile uint32_t *)0x40006418;
    uint32_t saved_ier = *CAN1_IER;
    *CAN1_IER = 0;
    /* Also clear any pending error flags before the busy-wait */
    *CAN1_ESR |= 0x00000070; /* Clear LEC[2:0] */

    /* Send via can_send_frame (fire-and-forget, proper mailbox management) */
    can_status_t ret = can_send_frame(
        req->channel, req->can_id, ide, rtr, req->dlc, req->data, 0);

    /* Poll for loopback RX (returns 0 immediately in normal mode) */
    int rx_found = can_poll_for_loopback_rx(req->channel, req->can_id, 10000000);

    /* Restore CAN interrupts */
    *CAN1_IER = saved_ier;

    /* Send CAN_FRAME_UP if loopback RX was received */
    if (rx_found) {
        can_frame_t rx_frame;
        memset(&rx_frame, 0, sizeof(rx_frame));
        rx_frame.id        = req->can_id;
        rx_frame.ide       = ide;
        rx_frame.rtr       = rtr;
        rx_frame.dlc       = req->dlc;
        rx_frame.channel   = req->channel;
        rx_frame.timestamp = device_get_uptime_us();
        memcpy(rx_frame.data, req->data, req->dlc > 8 ? 8 : req->dlc);
        protocol_send_can_frame(&rx_frame);
    }

    ack_resp_t ack;
    ack.ack_cmd    = CMD_CAN_SEND_FRAME;
    ack.error_code = (ret == CAN_OK) ? ERR_NONE : ERR_CAN_TX_FAILED;
    proto_send_data(MSG_ACK, (const uint8_t *)&ack, sizeof(ack));
}
/* CAN loopback diagnostic — delegates to can_driver */
static void handle_can_test(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;
    uint8_t result[20];
    extern int can_run_test(uint8_t *out, uint16_t maxlen);
    int len = can_run_test(result, sizeof(result));
    proto_send_data(MSG_ACK, result, (uint16_t)len);
}

static void handle_system_reset(const uint8_t *data, uint16_t data_len)
{
    (void)data;
    (void)data_len;

    /* Send ACK before reset */
    proto_send_simple(MSG_ACK);

    /* Small delay to allow TX to complete, then reset */
    for (volatile uint32_t i = 0; i < 100000; i++) { /* busy-wait */ }
    device_soft_reset();
}

/*============================================================================
 * Dispatch Table
 *============================================================================*/

typedef void (*cmd_handler_t)(const uint8_t *data, uint16_t data_len);

typedef struct {
    uint8_t cmd;
    cmd_handler_t handler;
} cmd_entry_t;

static const cmd_entry_t g_cmd_table[] = {
    { 0x05,                     handle_can_test },      /* CAN loopback diagnostic */
    { CMD_GET_INFO,             handle_get_info },
    { CMD_GET_CAPABILITIES,     handle_get_capabilities },
    { CMD_GET_STATUS,           handle_get_status },
    { CMD_GET_ADC_STATUS,       handle_get_adc_status },
    { CMD_CAN_SET_BAUDRATE,     handle_can_set_baudrate },
    { CMD_CAN_SET_MODE,         handle_can_set_mode },
    { CMD_CAN_SET_FILTER,       handle_can_set_filter },
    { CMD_ADC_SET_SAMPLING,     handle_adc_set_sampling },
    { CMD_COMM_SET_INTERFACE,   handle_comm_set_interface },
    { CMD_CAN_START_LISTEN,     handle_can_start_listen },
    { CMD_CAN_STOP_LISTEN,      handle_can_stop_listen },
    { CMD_ADC_START_SAMPLE,     handle_adc_start_sample },
    { CMD_ADC_STOP_SAMPLE,      handle_adc_stop_sample },
    { CMD_CAN_SEND_FRAME,       handle_can_send_frame },
    { CMD_SYSTEM_RESET,         handle_system_reset },
};

#define CMD_TABLE_SIZE (sizeof(g_cmd_table) / sizeof(g_cmd_table[0]))

/*============================================================================
 * Frame Validation
 *============================================================================*/

/**
 * @brief Validate a complete received frame.
 * @param buf       Raw frame buffer
 * @param total_len Total frame length from header
 * @return 0 if valid, negative on error
 */
static int proto_validate_frame(const uint8_t *buf, uint16_t total_len)
{
    if (total_len < PROTOCOL_FRAME_OVERHEAD) {
        return -1;
    }

    if (buf[0] != PROTOCOL_MAGIC_HEADER) {
        return -1;
    }

    uint16_t data_len = total_len - PROTOCOL_FRAME_OVERHEAD;

    /* Check end magic */
    if (buf[PROTOCOL_FRAME_HEADER_SIZE + data_len + 2] != PROTOCOL_END_MAGIC) {
        return -1;
    }

    /* Validate CRC */
    uint16_t computed = crc16_compute(buf, PROTOCOL_FRAME_HEADER_SIZE + data_len);
    uint16_t received = (uint16_t)(buf[PROTOCOL_FRAME_HEADER_SIZE + data_len])
                      | ((uint16_t)buf[PROTOCOL_FRAME_HEADER_SIZE + data_len + 1] << 8);

    if (computed != received) {
        return -2; /* CRC mismatch */
    }

    return 0;
}

/*============================================================================
 * Public API
 *============================================================================*/

/**
 * @brief Process incoming byte stream and dispatch complete frames.
 *        Call this from the main loop or from a comm RX callback.
 * @param byte      Incoming byte
 * @return 0 if no complete frame processed, 1 if a frame was handled, -1 on error
 */
int protocol_process_byte(uint8_t byte)
{
    /* State machine: wait for magic header */
    if (g_rx_buf_pos == 0) {
        if (byte != PROTOCOL_MAGIC_HEADER) {
            return 0; /* Not the start of a frame, discard */
        }
        g_rx_buf[g_rx_buf_pos++] = byte;
        g_rx_expected_len = 0;
        return 0;
    }

    /* Receiving frame header/data */
    if (g_rx_buf_pos < PROTOCOL_FRAME_TOTAL_MAX) {
        g_rx_buf[g_rx_buf_pos++] = byte;

        /* Once we have the length field (header bytes 1–2), compute expected length */
        if (g_rx_buf_pos == 3) {
            g_rx_expected_len = (uint16_t)g_rx_buf[1] | ((uint16_t)g_rx_buf[2] << 8);
            if (g_rx_expected_len > PROTOCOL_FRAME_TOTAL_MAX || g_rx_expected_len < PROTOCOL_FRAME_OVERHEAD) {
                /* Invalid length, reset */
                g_rx_buf_pos = 0;
                return -1;
            }
        }

        /* Check if we have a complete frame */
        if (g_rx_expected_len > 0 && g_rx_buf_pos >= g_rx_expected_len) {
            /* Validate and dispatch */
            int valid = proto_validate_frame(g_rx_buf, g_rx_expected_len);
            if (valid == 0) {
                uint8_t cmd = g_rx_buf[3];
                uint16_t data_len = PROTO_GET_DATA_LEN(g_rx_expected_len);

                /* Lookup and execute handler */
                int handled = 0;
                for (size_t i = 0; i < CMD_TABLE_SIZE; i++) {
                    if (g_cmd_table[i].cmd == cmd) {
                        g_cmd_table[i].handler(
                            &g_rx_buf[PROTOCOL_FRAME_HEADER_SIZE], data_len);
                        handled = 1;
                        break;
                    }
                }
                /* Send NACK for any unhandled App→FW command */
                if (!handled && cmd != 0x00) {
                    proto_send_simple(MSG_NACK);
                }
            }

            g_rx_buf_pos = 0;
            g_rx_expected_len = 0;
            return 1;
        }

        return 0;
    }

    /* Buffer overflow, reset */
    g_rx_buf_pos = 0;
    g_rx_expected_len = 0;
    return -1;
}

/**
 * @brief Feed a buffer of received bytes into the protocol processor.
 * @param data      Byte buffer
 * @param length    Number of bytes
 */
void protocol_process_buffer(const uint8_t *data, uint16_t length)
{
    for (uint16_t i = 0; i < length; i++) {
        protocol_process_byte(data[i]);
    }
}

/**
 * @brief Send a CAN frame upload notification to the App.
 * @param frame     Received CAN frame
 */
void protocol_send_can_frame(const can_frame_t *frame)
{
    can_frame_up_t up;
    memset(&up, 0, sizeof(up));
    up.timestamp = frame->timestamp;
    up.can_id    = frame->id;
    up.dlc       = frame->dlc;
    up.channel   = frame->channel;
    if (frame->ide)            up.flags |= 0x01;
    if (frame->rtr)            up.flags |= 0x02;
    if (frame->is_error_frame) up.flags |= 0x04;
    memcpy(up.data, frame->data, frame->dlc > 8 ? 8 : frame->dlc);

    if (frame->is_error_frame && frame->error_flags != 0) {
        /* Also send an error notification */
        error_notify_t err;
        memset(&err, 0, sizeof(err));
        err.source_module = 0; /* CAN */
        err.error_flags   = (uint16_t)(frame->error_flags & 0xFFFF);
        err.timestamp     = frame->timestamp;
        err.error_code    = ERR_HARDWARE_FAULT;
        proto_send_data(MSG_ERROR_NOTIFY, (const uint8_t *)&err, sizeof(err));
    }

    proto_send_data(MSG_CAN_FRAME_UP, (const uint8_t *)&up, sizeof(up));
}

/**
 * @brief Send an ADC data upload notification to the App.
 * @param data      ADC sample data
 */
void protocol_send_adc_data(const adc_sample_data_t *data)
{
    /* Use static buffer to avoid heap allocation on embedded targets */
    static uint8_t s_adc_tx_buf[PROTOCOL_FRAME_TOTAL_MAX];

    uint16_t payload_hdr_size = sizeof(adc_data_up_t) - sizeof(uint16_t);
    uint16_t sample_bytes = data->count * sizeof(uint16_t);

    /* Cap to buffer limit */
    uint16_t max_samples = (PROTOCOL_FRAME_DATA_MAX - payload_hdr_size) / sizeof(uint16_t);
    if (data->count > max_samples) {
        /* Send only the first batch; caller should iterate for remaining */
        sample_bytes = max_samples * sizeof(uint16_t);
    }
    uint16_t actual_count = sample_bytes / sizeof(uint16_t);
    uint16_t total_payload = payload_hdr_size + sample_bytes;

    memset(s_adc_tx_buf, 0, sizeof(s_adc_tx_buf));
    adc_data_up_t *up = (adc_data_up_t *)s_adc_tx_buf;
    up->timestamp   = data->timestamp;
    up->sample_rate = 0;
    up->sample_count = actual_count;
    up->resolution  = data->resolution;
    up->channel     = 0;
    up->mode        = (uint8_t)data->source;
    memcpy(up->samples, data->buffer, sample_bytes);

    proto_send_data(MSG_ADC_DATA_UP, s_adc_tx_buf, total_payload);
}

/**
 * @brief Send a device heartbeat frame (called once on boot).
 * @return 0 on success
 */
int protocol_send_heartbeat(void)
{
    device_heartbeat_t hb;
    memset(&hb, 0, sizeof(hb));
    device_info_t info;
    device_get_info(&info);
    strncpy(hb.mcu_model, info.mcu_model, sizeof(hb.mcu_model) - 1);
    hb.fw_major = info.fw_major;
    hb.fw_minor = info.fw_minor;
    hb.fw_patch = info.fw_patch;
    hb.comm_interface = (uint8_t)comm_get_current_interface();

    return proto_send_data(MSG_DEVICE_HEARTBEAT,
                           (const uint8_t *)&hb, sizeof(hb));
}

/**
 * @brief Reset the protocol parser state machine.
 */
void protocol_reset(void)
{
    g_rx_buf_pos = 0;
    g_rx_expected_len = 0;
    g_seq_counter = 0;
}
