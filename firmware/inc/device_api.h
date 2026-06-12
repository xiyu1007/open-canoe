/**
 * @file    device_api.h
 * @brief   Hardware-abstracted device information and capability query API.
 */

#ifndef DEVICE_API_H
#define DEVICE_API_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * Type Definitions
 *============================================================================*/

typedef struct {
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  fw_patch;
    char     mcu_model[32];
    char     fw_description[32];
    uint32_t device_serial;
} device_info_t;

typedef struct {
    uint32_t capability_bits;       /* Bitmap (CAP_* flags from protocol.h) */
    uint8_t  can_channel_count;
    uint32_t max_adc_sample_rate;
    uint8_t  adc_resolution_bits;
    uint16_t max_can_baudrate_kbps;
} device_capabilities_t;

/*============================================================================
 * API Functions
 *============================================================================*/

/**
 * @brief Get the MCU model string (e.g., "STM32F103C8T6").
 * @return Constant string pointer
 */
const char *device_get_mcu_model(void);

/**
 * @brief Get firmware version.
 * @param major  Output: major version
 * @param minor  Output: minor version
 * @param patch  Output: patch version
 */
void device_get_fw_version(uint8_t *major, uint8_t *minor, uint8_t *patch);

/**
 * @brief Get the unique device serial number.
 *        On STM32, this is derived from the 96-bit unique ID register.
 * @return 32-bit device serial (e.g., CRC32 of unique ID)
 */
uint32_t device_get_serial(void);

/**
 * @brief Get full device information (model, version, serial, description).
 * @param info  Output structure filled with device information
 */
void device_get_info(device_info_t *info);

/**
 * @brief Get device capabilities (ADC, CAN, USB, etc.).
 * @param caps  Output structure filled with capability data
 */
void device_get_capabilities(device_capabilities_t *caps);

/**
 * @brief Get MCU uptime since boot.
 * @return Uptime in milliseconds
 */
uint32_t device_get_uptime_ms(void);

/**
 * @brief Get MCU uptime since boot with microsecond precision.
 * @return Uptime in microseconds (rolls over at 32-bit limit)
 */
uint32_t device_get_uptime_us(void);

/**
 * @brief Perform a software reset of the MCU.
 */
void device_soft_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* DEVICE_API_H */
