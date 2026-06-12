/**
 * @file    protocol.h
 * @brief   Communication protocol definitions for App <-> Hardware interaction.
 * @note    This file is hardware-independent and can be shared with the App side.
 */

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * Protocol Constants
 *============================================================================*/
#define PROTOCOL_MAGIC_HEADER       0xA5U
#define PROTOCOL_FRAME_HEADER_SIZE  6U    /* magic(1) + length(2) + cmd(1) + seq(2) */
#define PROTOCOL_FRAME_FOOTER_SIZE  3U    /* CRC16(2) + end_magic(1) */
#define PROTOCOL_FRAME_OVERHEAD     (PROTOCOL_FRAME_HEADER_SIZE + PROTOCOL_FRAME_FOOTER_SIZE)
#define PROTOCOL_FRAME_DATA_MAX     256U
#define PROTOCOL_FRAME_TOTAL_MAX    (PROTOCOL_FRAME_OVERHEAD + PROTOCOL_FRAME_DATA_MAX)
#define PROTOCOL_END_MAGIC          0x5AU

#define PROTOCOL_VERSION_MAJOR      1U
#define PROTOCOL_VERSION_MINOR      0U

/*============================================================================
 * Command Codes
 *============================================================================*/
typedef enum {
    /* ---- Info Query (0x00–0x0F) ---- */
    CMD_GET_INFO            = 0x01,   /* Query firmware version, MCU model */
    CMD_GET_CAPABILITIES    = 0x02,   /* Query capability bitmap */
    CMD_GET_STATUS          = 0x03,   /* Query current running status */
    CMD_GET_ADC_STATUS      = 0x04,   /* Query ADC status (enabled, sampling, etc.) */

    /* ---- Parameter Config (0x10–0x2F) ---- */
    CMD_CAN_SET_BAUDRATE    = 0x10,   /* Set CAN baudrate */
    CMD_CAN_SET_MODE        = 0x11,   /* Set CAN work mode (normal, listen-only, loopback) */
    CMD_CAN_SET_FILTER      = 0x12,   /* Configure CAN filter */
    CMD_ADC_SET_SAMPLING    = 0x20,   /* Set ADC sampling rate / resolution */
    CMD_COMM_SET_INTERFACE  = 0x28,   /* Select active communication interface */

    /* ---- Control (0x30–0x4F) ---- */
    CMD_CAN_START_LISTEN    = 0x30,   /* Start CAN message listening */
    CMD_CAN_STOP_LISTEN     = 0x31,   /* Stop CAN message listening */
    CMD_ADC_START_SAMPLE    = 0x32,   /* Start ADC waveform sampling */
    CMD_ADC_STOP_SAMPLE     = 0x33,   /* Stop ADC waveform sampling */
    CMD_CAN_SEND_FRAME      = 0x34,   /* Send a single CAN frame */
    CMD_SYSTEM_RESET        = 0x3F,   /* Soft reset the MCU */

    /* ---- Responses / Notifications (0x80–0x9F) ---- */
    MSG_INFO_RESPONSE       = 0x81,   /* Response to CMD_GET_INFO */
    MSG_CAPABILITIES_RESP   = 0x82,   /* Response to CMD_GET_CAPABILITIES */
    MSG_STATUS_RESPONSE     = 0x83,   /* Response to CMD_GET_STATUS */
    MSG_ADC_STATUS_RESP     = 0x84,   /* Response to CMD_GET_ADC_STATUS */
    MSG_CAN_FRAME_UP        = 0x90,   /* CAN frame upload (Rx or Tx confirmation) */
    MSG_ADC_DATA_UP         = 0x91,   /* ADC waveform data upload */
    MSG_ERROR_NOTIFY        = 0x92,   /* Error notification */
    MSG_DEVICE_HEARTBEAT    = 0x93,   /* Device identification heartbeat on boot */
    MSG_ACK                 = 0xA0,   /* Generic ACK */
    MSG_NACK                = 0xA1,   /* Generic NACK with error code */

    CMD_INVALID             = 0xFF
} protocol_cmd_t;

/*============================================================================
 * Error Codes
 *============================================================================*/
typedef enum {
    ERR_NONE                = 0x00,
    ERR_INVALID_CMD         = 0x01,
    ERR_INVALID_PARAM       = 0x02,
    ERR_CRC_MISMATCH        = 0x03,
    ERR_BUFFER_OVERFLOW     = 0x04,
    ERR_TIMEOUT             = 0x05,
    ERR_CAN_BUS_OFF         = 0x10,
    ERR_CAN_ERROR_PASSIVE   = 0x11,
    ERR_CAN_TX_FAILED       = 0x12,
    ERR_CAN_RX_OVERRUN      = 0x13,
    ERR_ADC_NOT_AVAILABLE   = 0x20,
    ERR_ADC_OVERRUN         = 0x21,
    ERR_COMM_TX_FAILED      = 0x30,
    ERR_COMM_RX_OVERRUN     = 0x31,
    ERR_NOT_INITIALIZED     = 0x40,
    ERR_ALREADY_RUNNING     = 0x41,
    ERR_HARDWARE_FAULT      = 0xFF
} protocol_error_t;

/*============================================================================
 * Undefine HAL macros that conflict with our protocol enum names.
 * protocol.h is HAL-free but may be included after HAL headers.
 *============================================================================*/
#ifdef CAN_MODE_NORMAL
#undef CAN_MODE_NORMAL
#undef CAN_MODE_SILENT
#undef CAN_MODE_LOOPBACK
#undef CAN_MODE_SILENT_LOOPBACK
#endif
#ifdef CAN_FILTERMODE_IDMASK
#undef CAN_FILTERMODE_IDMASK
#undef CAN_FILTERMODE_IDLIST
#endif
#ifdef CAN_FILTERSCALE_16BIT
#undef CAN_FILTERSCALE_16BIT
#undef CAN_FILTERSCALE_32BIT
#endif

/*============================================================================
 * CAN Work Modes
 *============================================================================*/
typedef enum {
    CAN_MODE_NORMAL         = 0x00,
    CAN_MODE_LISTEN_ONLY    = 0x01,
    CAN_MODE_LOOPBACK       = 0x02,
    CAN_MODE_LOOPBACK_SILENT = 0x03
} can_mode_t;

/*============================================================================
 * Communication Interface Type
 *============================================================================*/
typedef enum {
    COMM_IF_USART           = 0x00,
    COMM_IF_USB_CDC         = 0x01
} comm_interface_t;

/*============================================================================
 * Capability Bitmap Bits
 *============================================================================*/
#define CAP_ADC                 (1U << 0)
#define CAP_USB_CDC             (1U << 1)
#define CAP_MULTI_CAN           (1U << 2)
#define CAP_TIMESTAMP_US        (1U << 3)

/*============================================================================
 * CAN Filter Configuration
 * NOTE: CAN error bitmask flags (CAN_ERR_*) are defined in can_api.h.
 *============================================================================*/
typedef enum {
    CAN_FILTER_MODE_ID_MASK     = 0x00,
    CAN_FILTER_MODE_ID_LIST     = 0x01
} can_filter_mode_t;

typedef enum {
    CAN_FILTER_SCALE_16BIT      = 0x00,
    CAN_FILTER_SCALE_32BIT      = 0x01
} can_filter_scale_t;

/*============================================================================
 * Protocol Frame Structures
 *============================================================================*/

#pragma pack(push, 1)

/**
 * @brief Generic protocol frame header (all frames start with this).
 */
typedef struct {
    uint8_t  magic;          /* PROTOCOL_MAGIC_HEADER */
    uint16_t length;         /* Total frame length including header, data, footer */
    uint8_t  cmd;            /* Command code (protocol_cmd_t) */
    uint16_t seq;            /* Sequence number for matching request/response */
} proto_header_t;

/**
 * @brief Frame layout: [header] [data...] [crc16] [end_magic]
 */
typedef struct {
    proto_header_t header;
    uint8_t        data[PROTOCOL_FRAME_DATA_MAX];
    /* CRC16 and END_MAGIC follow data area; accessed via helper macros */
} proto_frame_t;

/**
 * @brief CAN frame upload payload (MSG_CAN_FRAME_UP).
 */
typedef struct {
    uint32_t timestamp;        /* Hardware timestamp in μs (or 0 if unavailable) */
    uint32_t can_id;           /* CAN ID (standard 11-bit or extended 29-bit) */
    uint8_t  dlc;              /* Data Length Code (0–8) */
    uint8_t  flags;            /* bit0: IDE (1=extended), bit1: RTR, bit2: error_frame */
    uint8_t  data[8];          /* CAN data bytes */
    uint8_t  channel;          /* CAN channel index (0 = CAN1, 1 = CAN2, ...) */
} can_frame_up_t;

/**
 * @brief ADC waveform data payload (MSG_ADC_DATA_UP).
 */
typedef struct {
    uint32_t timestamp;        /* Sample start timestamp in μs */
    uint32_t sample_rate;      /* Actual sample rate used (Hz) */
    uint16_t sample_count;     /* Number of samples in this packet */
    uint16_t resolution;       /* ADC resolution bits (e.g., 12) */
    uint8_t  channel;          /* ADC channel index */
    uint8_t  mode;             /* 0 = ADC hardware, 1 = logic-level only */
    uint16_t samples[1];       /* Variable-length array of samples */
} adc_data_up_t;

/**
 * @brief Capability response payload (MSG_CAPABILITIES_RESP).
 */
typedef struct {
    uint32_t capability_bits;  /* Bitmap (CAP_* flags) */
    uint8_t  can_channel_count;/* Number of CAN channels */
    uint32_t max_adc_sample_rate; /* Max ADC sample rate in Hz (0 if no ADC) */
    uint8_t  adc_resolution;   /* ADC resolution in bits (0 if no ADC) */
    uint16_t max_can_baudrate; /* Maximum CAN baudrate in kbps */
} capabilities_resp_t;

/**
 * @brief Device info response payload (MSG_INFO_RESPONSE).
 */
typedef struct {
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  fw_patch;
    uint8_t  reserved;
    uint16_t protocol_version; /* (major << 8) | minor */
    char     mcu_model[32];
    char     fw_description[32];
    uint32_t device_serial;    /* Unique 32-bit device ID */
} device_info_resp_t;

/**
 * @brief CAN config payload (CMD_CAN_SET_BAUDRATE).
 */
typedef struct {
    uint32_t baudrate;         /* Desired baudrate in Hz */
    uint8_t  channel;          /* CAN channel index */
} can_set_baudrate_t;

/**
 * @brief CAN mode config payload (CMD_CAN_SET_MODE).
 */
typedef struct {
    uint8_t channel;
    uint8_t mode;              /* can_mode_t */
} can_set_mode_t;

/**
 * @brief CAN filter config payload (CMD_CAN_SET_FILTER).
 */
typedef struct {
    uint8_t  channel;
    uint8_t  filter_index;
    uint8_t  filter_mode;      /* can_filter_mode_t */
    uint8_t  filter_scale;     /* can_filter_scale_t */
    uint32_t id_high;
    uint32_t id_low;
    uint32_t mask_high;
    uint32_t mask_low;
} can_set_filter_t;

/**
 * @brief CAN frame to send payload (CMD_CAN_SEND_FRAME).
 */
typedef struct {
    uint32_t can_id;
    uint8_t  dlc;
    uint8_t  flags;            /* bit0: IDE, bit1: RTR */
    uint8_t  channel;
    uint8_t  data[8];
} can_send_frame_t;

/**
 * @brief ADC config payload (CMD_ADC_SET_SAMPLING).
 */
typedef struct {
    uint32_t sample_rate;      /* Desired sample rate in Hz */
    uint8_t  resolution;       /* Desired resolution in bits */
    uint8_t  channel;          /* ADC channel */
} adc_set_sampling_t;

/**
 * @brief Communication interface config payload (CMD_COMM_SET_INTERFACE).
 */
typedef struct {
    uint8_t interface;         /* comm_interface_t */
} comm_set_interface_t;

/**
 * @brief Error notification payload (MSG_ERROR_NOTIFY).
 */
typedef struct {
    uint8_t  error_code;       /* protocol_error_t */
    uint8_t  source_module;    /* 0=CAN, 1=ADC, 2=COMM, 3=SYSTEM */
    uint16_t error_flags;      /* Module-specific error flags */
    uint32_t timestamp;
} error_notify_t;

/**
 * @brief Status response payload (MSG_STATUS_RESPONSE).
 */
typedef struct {
    uint8_t  can_listening;    /* 1 if CAN listening is active */
    uint8_t  adc_sampling;     /* 1 if ADC sampling is active */
    uint8_t  comm_interface;   /* Current comm interface (comm_interface_t) */
    uint8_t  can_channels_active; /* Bitmap of active CAN channels */
    uint32_t uptime_ms;        /* MCU uptime in milliseconds */
} status_resp_t;

/**
 * @brief ACK/NACK payload.
 */
typedef struct {
    uint8_t  ack_cmd;          /* Original command being acknowledged */
    uint8_t  error_code;       /* 0 = success, else error (protocol_error_t) */
} ack_resp_t;

/**
 * @brief Device heartbeat payload (MSG_DEVICE_HEARTBEAT, sent on boot).
 */
typedef struct {
    char     mcu_model[32];
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  fw_patch;
    uint8_t  comm_interface;   /* The interface this heartbeat was sent on */
} device_heartbeat_t;

#pragma pack(pop)

/*============================================================================
 * Protocol Utility Macros
 *============================================================================*/

/** Compute full frame length from data length */
#define PROTO_CALC_LENGTH(data_len) \
    ((uint16_t)((data_len) + PROTOCOL_FRAME_OVERHEAD))

/** Extract data length from frame length field */
#define PROTO_GET_DATA_LEN(frame_len) \
    ((uint16_t)((frame_len) - PROTOCOL_FRAME_OVERHEAD))

/** Get pointer to data area within frame buffer */
#define PROTO_DATA_PTR(frame_buf) \
    ((uint8_t *)(frame_buf) + PROTOCOL_FRAME_HEADER_SIZE)

/** Get pointer to CRC field (right after data, at offset header+data_len) */
#define PROTO_CRC_PTR(frame_buf, data_len) \
    ((uint8_t *)(frame_buf) + PROTOCOL_FRAME_HEADER_SIZE + (data_len))

/** Get pointer to end magic byte */
#define PROTO_END_PTR(frame_buf, data_len) \
    ((uint8_t *)(frame_buf) + PROTOCOL_FRAME_HEADER_SIZE + (data_len) + 2)

#ifdef __cplusplus
}
#endif

#endif /* PROTOCOL_H */
