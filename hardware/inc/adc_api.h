/**
 * @file    adc_api.h
 * @brief   Hardware-abstracted ADC waveform acquisition API.
 * @note    ADC is optional — all functions degrade gracefully if HAS_ADC=0.
 */

#ifndef ADC_API_H
#define ADC_API_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * Type Definitions
 *============================================================================*/

typedef enum {
    ADC_OK              = 0,
    ADC_ERR_PARAM       = -1,
    ADC_ERR_NOT_INIT    = -2,
    ADC_ERR_NOT_AVAIL   = -3,
    ADC_ERR_BUSY        = -4,
    ADC_ERR_OVERRUN     = -5,
    ADC_ERR_HW          = -6
} adc_status_t;

typedef enum {
    ADC_SOURCE_ADC      = 0,    /* Hardware ADC sampling */
    ADC_SOURCE_LOGIC    = 1     /* Logic-level only (no ADC) */
} adc_source_t;

typedef struct {
    uint32_t sample_rate;       /* Sample rate in Hz */
    uint8_t  resolution;        /* ADC resolution in bits (e.g., 12) */
    uint8_t  channel;           /* ADC channel number */
    adc_source_t source;        /* Sampling source */
} adc_config_t;

typedef struct {
    uint32_t timestamp;         /* Sample start timestamp in μs */
    uint16_t *buffer;           /* Pointer to sample data buffer */
    uint16_t count;             /* Number of valid samples in buffer */
    uint16_t buffer_size;       /* Max capacity of buffer */
    uint8_t  resolution;        /* ADC resolution used */
    adc_source_t source;        /* Source used for this data */
} adc_sample_data_t;

/* Callback for ADC data ready (from ISR context when in DMA/interrupt mode) */
typedef void (*adc_data_ready_callback_t)(const adc_sample_data_t *data);

/*============================================================================
 * API Functions
 *============================================================================*/

/**
 * @brief Check if ADC hardware is available on this MCU.
 * @return 1 if ADC is available and configured, 0 otherwise
 */
uint8_t adc_is_available(void);

/**
 * @brief Initialize ADC for waveform sampling.
 * @param config    Sample rate, resolution, channel configuration
 * @return ADC_OK on success, ADC_ERR_NOT_AVAIL if no ADC hardware
 */
adc_status_t adc_init(const adc_config_t *config);

/**
 * @brief De-initialize ADC and release resources.
 * @return ADC_OK on success
 */
adc_status_t adc_deinit(void);

/**
 * @brief Start ADC sampling (continuous mode with DMA or interrupt).
 * @return ADC_OK on success, ADC_ERR_NOT_INIT if not configured
 */
adc_status_t adc_start_sampling(void);

/**
 * @brief Stop ADC sampling.
 * @return ADC_OK on success
 */
adc_status_t adc_stop_sampling(void);

/**
 * @brief Read the latest batch of ADC samples (polling mode).
 * @param data      Output structure with sample buffer pointer and count
 * @param timeout_ms Timeout in ms (0 = return immediately)
 * @return ADC_OK on success, ADC_ERR_TIMEOUT if no data available
 */
adc_status_t adc_read_samples(adc_sample_data_t *data, uint32_t timeout_ms);

/**
 * @brief Register callback for ADC data ready notification (DMA/IRQ mode).
 * @param callback  Callback function (NULL to deregister)
 * @return ADC_OK on success
 */
adc_status_t adc_register_data_callback(adc_data_ready_callback_t callback);

/**
 * @brief Query current ADC status.
 * @param is_sampling    Output: 1 if actively sampling
 * @param sample_rate    Output: current sample rate in Hz
 * @param resolution     Output: current resolution in bits
 * @return ADC_OK on success
 */
adc_status_t adc_get_status(uint8_t *is_sampling, uint32_t *sample_rate,
                            uint8_t *resolution);

/**
 * @brief Get the maximum supported ADC sample rate.
 * @return Max sample rate in Hz (0 if no ADC)
 */
uint32_t adc_get_max_sample_rate(void);

/**
 * @brief Get the ADC resolution in bits.
 * @return Resolution (0 if no ADC)
 */
uint8_t adc_get_resolution(void);

#ifdef __cplusplus
}
#endif

#endif /* ADC_API_H */
