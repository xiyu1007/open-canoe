/**
 * @file    device_manager.c
 * @brief   Device information, capabilities, and uptime management.
 *          Uses device config macros — no MCU-specific register access.
 */

#include "device_api.h"
#include "device_config.h"
#include "protocol.h"
#include <string.h>

/* Include STM32 HAL for unique ID access */
#if defined(STM32F103xB)
#include "stm32f1xx_hal.h"
#elif defined(STM32F407xx)
#include "stm32f4xx_hal.h"
#endif

/*============================================================================
 * Version Definition
 *============================================================================*/
#define FW_VERSION_MAJOR    1
#define FW_VERSION_MINOR    0
#define FW_VERSION_PATCH    0
#define FW_DESCRIPTION      "Open-Canoe CAN Analyzer"

/*============================================================================
 * Microsecond Timer
 *
 * We use the TIMESTAMP_TIMER (TIM2) as a free-running 32-bit counter at
 * TIMESTAMP_TIMER_CLK_HZ (1 MHz) for microsecond-resolution timestamps.
 *============================================================================*/

static volatile uint32_t g_uptime_ms = 0;

/* Called from SysTick ISR (1ms interval) */
void device_tick_ms(void)
{
    g_uptime_ms++;
}

/*============================================================================
 * Public API Implementation
 *============================================================================*/

const char *device_get_mcu_model(void)
{
    return MCU_MODEL_STRING;
}

void device_get_fw_version(uint8_t *major, uint8_t *minor, uint8_t *patch)
{
    if (major) *major = FW_VERSION_MAJOR;
    if (minor) *minor = FW_VERSION_MINOR;
    if (patch) *patch = FW_VERSION_PATCH;
}

uint32_t device_get_serial(void)
{
    /* STM32 unique ID: 96 bits at base address 0x1FFFF7E8 (F1) or 0x1FFF7A10 (F4) */
#if defined(STM32F103xB)
    uint32_t *uid = (uint32_t *)0x1FFFF7E8;
#elif defined(STM32F407xx)
    uint32_t *uid = (uint32_t *)0x1FFF7A10;
#else
    uint32_t uid[3] = {0, 0, 0};
#endif
    /* Simple XOR hash of the 96-bit UID to produce a 32-bit serial */
    return uid[0] ^ uid[1] ^ uid[2];
}

void device_get_info(device_info_t *info)
{
    if (!info) return;
    memset(info, 0, sizeof(*info));
    info->fw_major = FW_VERSION_MAJOR;
    info->fw_minor = FW_VERSION_MINOR;
    info->fw_patch = FW_VERSION_PATCH;
    info->device_serial = device_get_serial();
    strncpy(info->mcu_model, MCU_MODEL_STRING, sizeof(info->mcu_model) - 1);
    strncpy(info->fw_description, FW_DESCRIPTION, sizeof(info->fw_description) - 1);
}

void device_get_capabilities(device_capabilities_t *caps)
{
    if (!caps) return;
    memset(caps, 0, sizeof(*caps));

#if HAS_ADC
    caps->capability_bits |= CAP_ADC;
    caps->max_adc_sample_rate = ADC_SAMPLING_RATE_MAX_HZ;
    caps->adc_resolution_bits = ADC_RESOLUTION_BITS;
#endif

#if HAS_USB_CDC
    caps->capability_bits |= CAP_USB_CDC;
#endif

#if CAN_INSTANCE_COUNT > 1
    caps->capability_bits |= CAP_MULTI_CAN;
#endif

    caps->can_channel_count = CAN_INSTANCE_COUNT;
    caps->max_can_baudrate_kbps = 1000; /* bxCAN supports up to 1 Mbps */
    caps->capability_bits |= CAP_TIMESTAMP_US; /* We support μs timestamps */
}

uint32_t device_get_uptime_ms(void)
{
    return g_uptime_ms;
}

uint32_t device_get_uptime_us(void)
{
    /* Read TIM2 counter (free-running at TIMESTAMP_TIMER_CLK_HZ) */
    return (uint32_t)(TIMESTAMP_TIMER->CNT);
}

void device_soft_reset(void)
{
    __disable_irq();
    /* Request system reset via SCB AIRCR register */
    SCB->AIRCR = ((0x5FAUL << SCB_AIRCR_VECTKEY_Pos) |
                  (SCB->AIRCR & SCB_AIRCR_PRIGROUP_Msk) |
                  SCB_AIRCR_SYSRESETREQ_Msk);
    __DSB();
    while (1) { /* Wait for reset */ }
}
