/**
 * @file    adc_driver.c
 * @brief   ADC waveform acquisition driver using STM32 HAL.
 *          Degrades gracefully if ADC is unavailable (HAS_ADC=0).
 */

#include "adc_api.h"
#include "device_api.h"
#include "device_config.h"
#include <string.h>

#if HAS_ADC
#if defined(STM32F103xB)
#include "stm32f1xx_hal.h"
#include "stm32f1xx_hal_adc.h"
#include "stm32f1xx_hal_dma.h"
#elif defined(STM32F407xx)
#include "stm32f4xx_hal.h"
#include "stm32f4xx_hal_adc.h"
#include "stm32f4xx_hal_dma.h"
#endif
#endif

/*============================================================================
 * Internal State
 *============================================================================*/

#if HAS_ADC
static ADC_HandleTypeDef   g_adc_handle;
static DMA_HandleTypeDef   g_adc_dma_handle;
#endif

static adc_config_t        g_adc_config;
static uint8_t             g_adc_initialized = 0;
static uint8_t             g_adc_sampling    = 0;

static adc_data_ready_callback_t g_adc_callback = NULL;

/* Sample buffer (circular, filled by DMA) */
static uint16_t g_adc_buffer[ADC_SAMPLE_BUF_SIZE];

/*============================================================================
 * MSP Initialization
 *============================================================================*/

#if HAS_ADC
static void adc_msp_init(void)
{
    ADC_PERIPH_CLK_ENABLE();
    ADC_GPIO_CLK_ENABLE();

    /* Configure ADC input pin as analog */
    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_ANALOG;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Pin   = GPIO_PIN_0; /* ADC_CAN_MONITOR_CHANNEL → PA0 */
    HAL_GPIO_Init(GPIOA, &gpio);

    /* DMA for ADC (DMA2 Stream0 / DMA1 Channel1 depending on MCU) */
#if defined(STM32F103xB)
    __HAL_RCC_DMA1_CLK_ENABLE();
    g_adc_dma_handle.Instance = DMA1_Channel1;
#elif defined(STM32F407xx)
    __HAL_RCC_DMA2_CLK_ENABLE();
    g_adc_dma_handle.Instance = DMA2_Stream0;
    g_adc_dma_handle.Init.Channel = DMA_CHANNEL_0;
#endif

    g_adc_dma_handle.Init.Direction           = DMA_PERIPH_TO_MEMORY;
    g_adc_dma_handle.Init.PeriphInc           = DMA_PINC_DISABLE;
    g_adc_dma_handle.Init.MemInc              = DMA_MINC_ENABLE;
    g_adc_dma_handle.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
    g_adc_dma_handle.Init.MemDataAlignment    = DMA_MDATAALIGN_HALFWORD;
    g_adc_dma_handle.Init.Mode                = DMA_CIRCULAR;
    g_adc_dma_handle.Init.Priority            = DMA_PRIORITY_HIGH;

#if defined(STM32F407xx)
    g_adc_dma_handle.Init.FIFOMode            = DMA_FIFOMODE_DISABLE;
#endif

    HAL_DMA_Init(&g_adc_dma_handle);
    __HAL_LINKDMA(&g_adc_handle, DMA_Handle, g_adc_dma_handle);
}
#endif

/*============================================================================
 * Public API Implementation
 *============================================================================*/

uint8_t adc_is_available(void)
{
#if HAS_ADC
    return 1;
#else
    return 0;
#endif
}

adc_status_t adc_init(const adc_config_t *config)
{
    if (!config) return ADC_ERR_PARAM;

#if !HAS_ADC
    (void)config;
    return ADC_ERR_NOT_AVAIL;
#else
    /* If already sampling, stop first */
    if (g_adc_sampling) {
        adc_stop_sampling();
    }

    /* Cap sample rate to max */
    uint32_t rate = config->sample_rate;
    if (rate > ADC_SAMPLING_RATE_MAX_HZ) rate = ADC_SAMPLING_RATE_MAX_HZ;
    if (rate == 0) rate = 100000; /* Default 100 kHz */

    /* Cap resolution */
    uint8_t res = config->resolution;
    if (res > ADC_RESOLUTION_BITS) res = ADC_RESOLUTION_BITS;
    if (res == 0) res = 12;

    /* Configure ADC — different init struct per MCU family */
    memset(&g_adc_handle, 0, sizeof(g_adc_handle));
    g_adc_handle.Instance = ADC_INSTANCE;

#if defined(STM32F103xB)
    g_adc_handle.Init.DataAlign             = ADC_DATAALIGN_RIGHT;
    g_adc_handle.Init.ScanConvMode          = ADC_SCAN_DISABLE;
    g_adc_handle.Init.ContinuousConvMode    = ENABLE;
    g_adc_handle.Init.NbrOfConversion       = 1;
    g_adc_handle.Init.DiscontinuousConvMode = DISABLE;
    g_adc_handle.Init.NbrOfDiscConversion   = 0;
    g_adc_handle.Init.ExternalTrigConv      = ADC_SOFTWARE_START;
#elif defined(STM32F407xx)
    g_adc_handle.Init.ClockPrescaler        = ADC_CLOCK_SYNC_PCLK_DIV4;
    g_adc_handle.Init.Resolution            = ADC_RESOLUTION_12B;
    g_adc_handle.Init.DataAlign             = ADC_DATAALIGN_RIGHT;
    g_adc_handle.Init.ScanConvMode          = DISABLE;
    g_adc_handle.Init.ContinuousConvMode    = ENABLE;
    g_adc_handle.Init.NbrOfConversion       = 1;
    g_adc_handle.Init.DiscontinuousConvMode = DISABLE;
    g_adc_handle.Init.ExternalTrigConvEdge  = ADC_EXTERNALTRIGCONVEDGE_NONE;
    g_adc_handle.Init.ExternalTrigConv      = ADC_SOFTWARE_START;
    g_adc_handle.Init.DMAContinuousRequests = ENABLE;
    g_adc_handle.Init.EOCSelection          = ADC_EOC_SINGLE_CONV;
#endif

    adc_msp_init();

    if (HAL_ADC_Init(&g_adc_handle) != HAL_OK) {
        return ADC_ERR_HW;
    }

    /* Configure channel */
    ADC_ChannelConfTypeDef ch_conf = {0};
    ch_conf.Channel      = ADC_CAN_MONITOR_CHANNEL;
    ch_conf.Rank         = ADC_REGULAR_RANK_1;
    ch_conf.SamplingTime = ADC_SAMPLETIME_1CYCLE_5;

    if (HAL_ADC_ConfigChannel(&g_adc_handle, &ch_conf) != HAL_OK) {
        return ADC_ERR_HW;
    }

    /* Save config */
    memcpy(&g_adc_config, config, sizeof(adc_config_t));
    g_adc_config.sample_rate = rate;
    g_adc_config.resolution  = res;
    g_adc_initialized = 1;

    return ADC_OK;
#endif
}

adc_status_t adc_deinit(void)
{
#if HAS_ADC
    if (g_adc_sampling) adc_stop_sampling();
    if (g_adc_initialized) {
        HAL_ADC_DeInit(&g_adc_handle);
        HAL_DMA_DeInit(&g_adc_dma_handle);
    }
#endif
    g_adc_initialized = 0;
    return ADC_OK;
}

adc_status_t adc_start_sampling(void)
{
#if !HAS_ADC
    return ADC_ERR_NOT_AVAIL;
#else
    if (!g_adc_initialized) return ADC_ERR_NOT_INIT;
    if (g_adc_sampling) return ADC_OK; /* Already running */

    /* Start DMA */
    HAL_ADC_Start_DMA(&g_adc_handle,
                      (uint32_t *)g_adc_buffer,
                      ADC_SAMPLE_BUF_SIZE);

    g_adc_sampling = 1;
    return ADC_OK;
#endif
}

adc_status_t adc_stop_sampling(void)
{
#if !HAS_ADC
    return ADC_ERR_NOT_AVAIL;
#else
    if (!g_adc_sampling) return ADC_OK;

    HAL_ADC_Stop_DMA(&g_adc_handle);
    g_adc_sampling = 0;
    return ADC_OK;
#endif
}

adc_status_t adc_read_samples(adc_sample_data_t *data, uint32_t timeout_ms)
{
    if (!data) return ADC_ERR_PARAM;

#if !HAS_ADC
    (void)timeout_ms;
    memset(data, 0, sizeof(*data));
    return ADC_ERR_NOT_AVAIL;
#else
    if (!g_adc_initialized) return ADC_ERR_NOT_INIT;

    /* In continuous DMA mode, the buffer is always being filled.
     * Return the current DMA pointer position as a snapshot. */
    uint32_t dma_counter = __HAL_DMA_GET_COUNTER(&g_adc_dma_handle);
    uint16_t filled = ADC_SAMPLE_BUF_SIZE - (uint16_t)dma_counter;

    data->timestamp   = device_get_uptime_us();
    data->buffer      = g_adc_buffer;
    data->count       = filled;
    data->buffer_size = ADC_SAMPLE_BUF_SIZE;
    data->resolution  = g_adc_config.resolution;
    data->source      = g_adc_config.source;

    (void)timeout_ms;
    return ADC_OK;
#endif
}

adc_status_t adc_register_data_callback(adc_data_ready_callback_t callback)
{
    g_adc_callback = callback;
    return ADC_OK;
}

adc_status_t adc_get_status(uint8_t *is_sampling, uint32_t *sample_rate,
                            uint8_t *resolution)
{
    if (is_sampling)  *is_sampling  = g_adc_sampling;
    if (sample_rate)  *sample_rate  = g_adc_initialized ? g_adc_config.sample_rate : 0;
    if (resolution)   *resolution   = g_adc_initialized ? g_adc_config.resolution : 0;
    return ADC_OK;
}

uint32_t adc_get_max_sample_rate(void)
{
#if HAS_ADC
    return ADC_SAMPLING_RATE_MAX_HZ;
#else
    return 0;
#endif
}

uint8_t adc_get_resolution(void)
{
#if HAS_ADC
    return ADC_RESOLUTION_BITS;
#else
    return 0;
#endif
}

/*============================================================================
 * DMA Transfer Complete Callback (weak override from HAL)
 *============================================================================*/

#if HAS_ADC
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (g_adc_callback && hadc == &g_adc_handle) {
        adc_sample_data_t data;
        data.timestamp   = device_get_uptime_us();
        data.buffer      = g_adc_buffer;               /* First half */
        data.count       = ADC_SAMPLE_BUF_SIZE / 2;
        data.buffer_size = ADC_SAMPLE_BUF_SIZE;
        data.resolution  = g_adc_config.resolution;
        data.source      = g_adc_config.source;
        g_adc_callback(&data);
    }
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (g_adc_callback && hadc == &g_adc_handle) {
        adc_sample_data_t data;
        data.timestamp   = device_get_uptime_us();
        data.buffer      = g_adc_buffer + (ADC_SAMPLE_BUF_SIZE / 2); /* Second half */
        data.count       = ADC_SAMPLE_BUF_SIZE / 2;
        data.buffer_size = ADC_SAMPLE_BUF_SIZE;
        data.resolution  = g_adc_config.resolution;
        data.source      = g_adc_config.source;
        g_adc_callback(&data);
    }
}
#endif
