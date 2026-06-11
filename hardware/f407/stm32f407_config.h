/**
 * @file    stm32f407_config.h
 * @brief   MCU-specific configuration for STM32F407VET6
 * @note    Modify only this file when porting to a different F407 variant.
 *          Core driver code must NOT be changed.
 */

#ifndef STM32F407_CONFIG_H
#define STM32F407_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * MCU Identification
 *============================================================================*/
#define MCU_MODEL_STRING        "STM32F407VET6"
#define MCU_FAMILY_STRING       "STM32F4xx"
#define MCU_CORE_STRING         "Cortex-M4F"

/*============================================================================
 * Feature Availability Flags
 *============================================================================*/
#define HAS_ADC                 1       /* ADC1/2/3 available */
#define HAS_USB_CDC             1       /* USB OTG FS available for CDC */
#define HAS_CAN_LEGACY          1       /* F4 uses legacy CAN API by default */

/*============================================================================
 * System Clocks
 *============================================================================*/
#define SYSTEM_CLOCK_HZ         168000000UL
#define APB1_CLOCK_HZ           42000000UL   /* APB1 max 42 MHz */
#define APB2_CLOCK_HZ           84000000UL   /* APB2 max 84 MHz */
#define TIMESTAMP_TIMER_CLK_HZ  1000000UL    /* 1 MHz for μs timestamp resolution */

/*============================================================================
 * CAN Peripheral Configuration
 *============================================================================*/
#define CAN_INSTANCE_COUNT      2

/* CAN1 */
#define CAN1_PERIPH_CLK_ENABLE()    __HAL_RCC_CAN1_CLK_ENABLE()
#define CAN1_GPIO_CLK_ENABLE()      __HAL_RCC_GPIOB_CLK_ENABLE()
#define CAN1_PORT                   GPIOB
#define CAN1_RX_PIN                 GPIO_PIN_8
#define CAN1_TX_PIN                 GPIO_PIN_9
#define CAN1_IRQn                   CAN1_RX0_IRQn
#define CAN1_IRQHandler             CAN1_RX0_IRQHandler

/* CAN2 */
#define CAN2_PERIPH_CLK_ENABLE()    __HAL_RCC_CAN2_CLK_ENABLE()
#define CAN2_GPIO_CLK_ENABLE()      __HAL_RCC_GPIOB_CLK_ENABLE()
#define CAN2_PORT                   GPIOB
#define CAN2_RX_PIN                 GPIO_PIN_12
#define CAN2_TX_PIN                 GPIO_PIN_13
#define CAN2_IRQn                   CAN2_RX0_IRQn
#define CAN2_IRQHandler             CAN2_RX0_IRQHandler

/* bxCAN filter bank count (F407 has 28) */
#define CAN_FILTER_BANK_COUNT       28

/*============================================================================
 * Communication Interface Configuration
 *============================================================================*/

/* --- USART1 (default primary communication channel) --- */
#define COMM_USART                   USART1
#define COMM_USART_BAUDRATE          115200
#define COMM_USART_CLK_ENABLE()      __HAL_RCC_USART1_CLK_ENABLE()
#define COMM_USART_GPIO_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
#define COMM_USART_TX_PORT           GPIOA
#define COMM_USART_TX_PIN            GPIO_PIN_9
#define COMM_USART_RX_PORT           GPIOA
#define COMM_USART_RX_PIN            GPIO_PIN_10
#define COMM_USART_IRQn              USART1_IRQn
#define COMM_USART_IRQHandler        USART1_IRQHandler

/* Alternate debug/supplementary USART */
#define AUX_USART                    USART2
#define AUX_USART_CLK_ENABLE()       __HAL_RCC_USART2_CLK_ENABLE()
#define AUX_USART_GPIO_CLK_ENABLE()  __HAL_RCC_GPIOA_CLK_ENABLE()
#define AUX_USART_TX_PORT            GPIOA
#define AUX_USART_TX_PIN             GPIO_PIN_2
#define AUX_USART_RX_PORT            GPIOA
#define AUX_USART_RX_PIN             GPIO_PIN_3

/* --- USB CDC Configuration (alternate communication channel) --- */
#define USB_CDC_CLK_ENABLE()         __HAL_RCC_USB_OTG_FS_CLK_ENABLE()
#define USB_CDC_GPIO_CLK_ENABLE()    __HAL_RCC_GPIOA_CLK_ENABLE()
#define USB_CDC_DP_PORT              GPIOA
#define USB_CDC_DP_PIN               GPIO_PIN_12
#define USB_CDC_DM_PORT              GPIOA
#define USB_CDC_DM_PIN               GPIO_PIN_11
#define USB_CDC_ID_PORT              GPIOA
#define USB_CDC_ID_PIN               GPIO_PIN_10
#define USB_CDC_VBUS_PORT            GPIOA
#define USB_CDC_VBUS_PIN             GPIO_PIN_9
#define USB_CDC_IRQn                 OTG_FS_IRQn
#define USB_CDC_IRQHandler           OTG_FS_IRQHandler

/*============================================================================
 * ADC Configuration (Optional)
 *============================================================================*/
#define ADC_INSTANCE                 ADC1
#define ADC_SAMPLING_RATE_MAX_HZ     2400000UL   /* 2.4 Msps for F407 */
#define ADC_RESOLUTION_BITS          12
#define ADC_CHANNEL_COUNT            16
#define ADC_PERIPH_CLK_ENABLE()      __HAL_RCC_ADC1_CLK_ENABLE()
#define ADC_GPIO_CLK_ENABLE()        __HAL_RCC_GPIOA_CLK_ENABLE()
#define ADC_CAN_MONITOR_CHANNEL      ADC_CHANNEL_0   /* PA0 as CAN bus monitor input */

/*============================================================================
 * GPIO / Debug LED
 *============================================================================*/
#define DEBUG_LED_PORT               GPIOA
#define DEBUG_LED_PIN                GPIO_PIN_6    /* F407-DISC board LED */
#define DEBUG_LED_CLK_ENABLE()       __HAL_RCC_GPIOA_CLK_ENABLE()

/*============================================================================
 * Timestamp Timer
 *============================================================================*/
#define TIMESTAMP_TIMER              TIM2
#define TIMESTAMP_TIMER_CLK_ENABLE() __HAL_RCC_TIM2_CLK_ENABLE()
#define TIMESTAMP_TIMER_IRQn         TIM2_IRQn
#define TIMESTAMP_TIMER_IRQHandler   TIM2_IRQHandler

/*============================================================================
 * Buffer Sizes
 *============================================================================*/
#define CAN_RX_FIFO_SIZE             128
#define CAN_TX_FIFO_SIZE             64
#define COMM_RX_BUF_SIZE             512
#define COMM_TX_BUF_SIZE             1024
#define ADC_SAMPLE_BUF_SIZE          4096
#define PROTOCOL_FRAME_MAX_SIZE      512

#ifdef __cplusplus
}
#endif

#endif /* STM32F407_CONFIG_H */
