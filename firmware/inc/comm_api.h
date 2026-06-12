/**
 * @file    comm_api.h
 * @brief   Hardware-abstracted communication API (USART / USB-CDC).
 * @note    Supports switching between physical interfaces at runtime.
 */

#ifndef COMM_API_H
#define COMM_API_H

#include <stdint.h>
#include <stddef.h>
#include "protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * Type Definitions
 *============================================================================*/

typedef enum {
    COMM_OK             = 0,
    COMM_ERR_PARAM      = -1,
    COMM_ERR_NOT_INIT   = -2,
    COMM_ERR_TIMEOUT    = -3,
    COMM_ERR_TX_FAILED  = -4,
    COMM_ERR_RX_OVERRUN = -5,
    COMM_ERR_HW         = -6,
    COMM_ERR_SWITCH_FAILED = -7
} comm_status_t;

typedef struct {
    comm_interface_t type;      /* Interface type (from protocol.h) */
    uint32_t baudrate;          /* Baudrate (USART only; ignored for USB CDC) */
} comm_config_t;

/* Callback for received data */
typedef void (*comm_rx_callback_t)(const uint8_t *data, uint16_t length);

/*============================================================================
 * API Functions
 *============================================================================*/

/**
 * @brief Initialize the communication interface.
 * @param config    Interface type and baudrate
 * @return COMM_OK on success
 */
comm_status_t comm_init(const comm_config_t *config);

/**
 * @brief Switch active communication interface at runtime.
 *        The previous interface is stopped and the new one activated.
 * @param new_type  Target interface type
 * @param baudrate  Baudrate (for USART; ignored for USB CDC)
 * @return COMM_OK on success
 */
comm_status_t comm_switch_interface(comm_interface_t new_type, uint32_t baudrate);

/**
 * @brief Get the current active interface type.
 * @return Current interface type
 */
comm_interface_t comm_get_current_interface(void);

/**
 * @brief Send raw bytes over the active communication interface (blocking).
 * @param data      Pointer to data buffer
 * @param length    Number of bytes to send
 * @param timeout_ms Timeout in ms
 * @return COMM_OK on success, COMM_ERR_TX_FAILED on error
 */
comm_status_t comm_send(const uint8_t *data, uint16_t length,
                        uint32_t timeout_ms);

/**
 * @brief Receive raw bytes over the active communication interface.
 * @param buffer    Receive buffer
 * @param max_len   Maximum bytes to receive
 * @param recv_len  Output: actual bytes received
 * @param timeout_ms Timeout in ms (0 = non-blocking)
 * @return COMM_OK on success
 */
comm_status_t comm_receive(uint8_t *buffer, uint16_t max_len,
                           uint16_t *recv_len, uint32_t timeout_ms);

/**
 * @brief Register a callback for received data (interrupt mode).
 *        After registration, incoming bytes invoke the callback from ISR context.
 * @param callback  Callback function (NULL to deregister)
 * @return COMM_OK on success
 */
comm_status_t comm_register_rx_callback(comm_rx_callback_t callback);

/**
 * @brief Send the device identification heartbeat frame on boot.
 *        This is called once after initialization, before entering the main loop.
 * @return COMM_OK on success
 */
comm_status_t comm_send_heartbeat(void);

/**
 * @brief Flush the transmit buffer, ensuring all pending data is sent.
 * @return COMM_OK on success
 */
comm_status_t comm_flush_tx(void);

/**
 * @brief Query whether the current interface is connected/ready.
 * @return 1 if interface is initialized and ready, 0 otherwise
 */
uint8_t comm_is_ready(void);

/**
 * @brief Check if USB CDC interface is available on this MCU.
 * @return 1 if USB CDC is available, 0 otherwise
 */
uint8_t comm_usb_cdc_available(void);

#ifdef __cplusplus
}
#endif

#endif /* COMM_API_H */
