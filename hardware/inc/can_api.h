/**
 * @file    can_api.h
 * @brief   Hardware-abstracted CAN control API.
 * @note    All functions operate through the device config macros.
 *          No MCU-specific types or registers appear in this header.
 */

#ifndef CAN_API_H
#define CAN_API_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * Type Definitions
 *============================================================================*/

typedef enum {
    CAN_OK              = 0,
    CAN_ERR_PARAM       = -1,
    CAN_ERR_BUSY        = -2,
    CAN_ERR_TIMEOUT     = -3,
    CAN_ERR_NOT_INIT    = -4,
    CAN_ERR_HW          = -5,
    CAN_ERR_NO_BUFFER   = -6
} can_status_t;

typedef enum {
    CAN_RX_MODE_BLOCKING    = 0,
    CAN_RX_MODE_NONBLOCKING = 1,
    CAN_RX_MODE_INTERRUPT   = 2
} can_rx_mode_t;

/* CAN Error Bitmask Flags (used by can_get_error_status, can_frame_t.error_flags) */
#define CAN_ERR_CRC             (1U << 0)
#define CAN_ERR_BIT_STUFFING    (1U << 1)
#define CAN_ERR_ACK             (1U << 2)
#define CAN_ERR_FORM            (1U << 3)
#define CAN_ERR_BUS_OFF         (1U << 4)
#define CAN_ERR_PASSIVE         (1U << 5)
#define CAN_ERR_WARNING         (1U << 6)
#define CAN_ERR_RX_OVERRUN      (1U << 7)

typedef struct {
    uint32_t id;            /* CAN message ID (11-bit or 29-bit) */
    uint8_t  data[8];       /* Payload data */
    uint8_t  dlc;           /* Data length (0–8) */
    uint8_t  ide;           /* 0 = standard, 1 = extended ID */
    uint8_t  rtr;           /* 0 = data frame, 1 = remote frame */
    uint8_t  channel;       /* CAN channel (0-based) */
    uint32_t timestamp;     /* Timestamp in μs when frame was received */
    uint8_t  is_error_frame;/* 1 if this is an error frame notification */
    uint32_t error_flags;   /* Error type flags (CAN_ERR_*) */
} can_frame_t;

typedef struct {
    uint32_t baudrate;      /* CAN baudrate in Hz */
    uint8_t  mode;          /* 0 = normal, 1 = listen-only, 2 = loopback, 3 = loopback+silent */
    uint8_t  channel;       /* CAN channel index */
} can_config_t;

typedef struct {
    uint32_t tx_success;    /* Successful transmissions */
    uint32_t tx_failed;     /* Failed transmissions */
    uint32_t rx_received;   /* Successfully received frames */
    uint32_t rx_lost;       /* Lost frames (overrun) */
    uint32_t error_count;   /* Total error events */
    uint32_t bus_off_count; /* Bus-off events */
} can_stats_t;

/* Callback type for received CAN frames */
typedef void (*can_rx_callback_t)(const can_frame_t *frame);

/*============================================================================
 * API Functions
 *============================================================================*/

/**
 * @brief Initialize CAN peripheral(s) for the given channel.
 * @param channel   CAN channel index (0 for CAN1, 1 for CAN2, ...)
 * @param config    Baudrate and mode configuration
 * @return CAN_OK on success, error code otherwise
 */
can_status_t can_init(uint8_t channel, const can_config_t *config);

/**
 * @brief De-initialize CAN peripheral.
 * @param channel   CAN channel index
 * @return CAN_OK on success
 */
can_status_t can_deinit(uint8_t channel);

/**
 * @brief Reconfigure CAN baudrate at runtime.
 * @param channel   CAN channel index
 * @param baudrate  New baudrate in Hz
 * @return CAN_OK on success
 */
can_status_t can_set_baudrate(uint8_t channel, uint32_t baudrate);

/**
 * @brief Set CAN working mode.
 * @param channel   CAN channel index
 * @param mode      0=normal, 1=listen-only, 2=loopback, 3=loopback+silent
 * @return CAN_OK on success
 */
can_status_t can_set_mode(uint8_t channel, uint8_t mode);

/**
 * @brief Configure a CAN filter bank.
 * @param channel       CAN channel index
 * @param filter_index  Filter bank number
 * @param filter_mode   0=id_mask, 1=id_list
 * @param filter_scale  0=16bit, 1=32bit
 * @param id_high       Filter ID high
 * @param id_low        Filter ID low
 * @param mask_high     Mask high (for mask mode)
 * @param mask_low      Mask low (for mask mode)
 * @return CAN_OK on success
 */
can_status_t can_set_filter(uint8_t channel, uint8_t filter_index,
                            uint8_t filter_mode, uint8_t filter_scale,
                            uint32_t id_high, uint32_t id_low,
                            uint32_t mask_high, uint32_t mask_low);

/**
 * @brief Send a CAN frame.
 * @param channel   CAN channel index
 * @param id        CAN message ID
 * @param ide       0=standard, 1=extended
 * @param rtr       0=data, 1=remote
 * @param dlc       Data length (0–8)
 * @param data      Pointer to data bytes (NULL if dlc=0)
 * @param timeout_ms Timeout in ms (0 = non-blocking)
 * @return CAN_OK on success, CAN_ERR_TIMEOUT if timeout, CAN_ERR_NO_BUFFER if TX mailbox full
 */
can_status_t can_send_frame(uint8_t channel, uint32_t id, uint8_t ide,
                            uint8_t rtr, uint8_t dlc, const uint8_t *data,
                            uint32_t timeout_ms);

/**
 * @brief Receive a CAN frame (blocking or non-blocking).
 * @param channel   CAN channel index
 * @param frame     Output buffer for received frame
 * @param timeout_ms Timeout in ms (0 = non-blocking, ANY = blocking)
 * @return CAN_OK on success, CAN_ERR_TIMEOUT if no frame available
 */
can_status_t can_receive_frame(uint8_t channel, can_frame_t *frame,
                               uint32_t timeout_ms);

/**
 * @brief Register a callback for CAN frame reception (interrupt mode).
 *        After registration, incoming frames invoke the callback from ISR context.
 * @param channel   CAN channel index
 * @param callback  Callback function pointer (NULL to deregister)
 * @return CAN_OK on success
 */
can_status_t can_register_rx_callback(uint8_t channel, can_rx_callback_t callback);

/**
 * @brief Start CAN listening (enables reception).
 * @param channel   CAN channel index
 * @return CAN_OK on success
 */
can_status_t can_start_listen(uint8_t channel);

/**
 * @brief Stop CAN listening (disables reception).
 * @param channel   CAN channel index
 * @return CAN_OK on success
 */
can_status_t can_stop_listen(uint8_t channel);

/**
 * @brief Get CAN error state.
 * @param channel       CAN channel index
 * @param error_flags   Output: bitmask of current errors (CAN_ERR_*)
 * @param tx_error_cnt  Output: transmit error counter
 * @param rx_error_cnt  Output: receive error counter
 * @return CAN_OK on success
 */
can_status_t can_get_error_status(uint8_t channel, uint32_t *error_flags,
                                  uint8_t *tx_error_cnt, uint8_t *rx_error_cnt);

/**
 * @brief Clear CAN error counters and reset error state.
 * @param channel   CAN channel index
 * @return CAN_OK on success
 */
can_status_t can_clear_errors(uint8_t channel);

/**
 * @brief Get CAN channel statistics.
 * @param channel   CAN channel index
 * @param stats     Output statistics structure
 * @return CAN_OK on success
 */
can_status_t can_get_stats(uint8_t channel, can_stats_t *stats);

/**
 * @brief Get the number of available CAN channels.
 * @return Number of CAN instances on this MCU
 */
uint8_t can_get_channel_count(void);

/**
 * @brief Query whether a specific CAN channel is initialized.
 * @param channel   CAN channel index
 * @return 1 if initialized, 0 otherwise
 */
uint8_t can_is_initialized(uint8_t channel);

#ifdef __cplusplus
}
#endif

#endif /* CAN_API_H */
