/**
 * @file    stm32f103_config.h
 * @brief   MCU-specific configuration for STM32F103C8T6
 * @note    Modify only this file when porting to a different F103 variant.
 *          Core driver code must NOT be changed.
 */

#ifndef STM32F103_CONFIG_H
#define STM32F103_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * MCU Identification
 *============================================================================*/
#define MCU_MODEL_STRING        "STM32F103C8T6"
#define MCU_FAMILY_STRING       "STM32F1xx"
#define MCU_CORE_STRING         "Cortex-M3"

/*============================================================================
 * Feature Availability Flags
 *============================================================================*/
#define HAS_ADC                 1       /* ADC1/ADC2 available */
#define HAS_USB_CDC             0       /* F103C8 does not have USB OTG */
#define HAS_CAN_LEGACY          1       /* F1 uses legacy CAN API */

/*============================================================================
 * System Clocks
 *============================================================================*/
/* HSI 8MHz /2 * PLL16 = 64MHz SYSCLK. APB1 = /2 = 32MHz, APB2 = /1 = 64MHz */
#define SYSTEM_CLOCK_HZ         64000000UL
#define APB1_CLOCK_HZ           32000000UL
#define APB2_CLOCK_HZ           64000000UL
#define TIMESTAMP_TIMER_CLK_HZ  1000000UL    /* 1 MHz for μs timestamp resolution */

/*============================================================================
 * CAN Peripheral Configuration
 *============================================================================*/
#define CAN_INSTANCE_COUNT      1

/* CAN1 — default pins PA11(RX)/PA12(TX), no remap */
#define CAN1_PERIPH_CLK_ENABLE()    __HAL_RCC_CAN1_CLK_ENABLE()
#define CAN1_GPIO_CLK_ENABLE()      __HAL_RCC_GPIOA_CLK_ENABLE()
#define CAN1_PORT                   GPIOA
#define CAN1_RX_PIN                 GPIO_PIN_11
#define CAN1_TX_PIN                 GPIO_PIN_12
#define CAN1_AFIO_REMAP()           /* no remap needed — default PA11/PA12 */
#define CAN1_AFIO_CLK_ENABLE()      /* no AFIO clock needed for default pins */
#define CAN1_IRQn                   USB_LP_CAN1_RX0_IRQn
#define CAN1_IRQHandler             USB_LP_CAN1_RX0_IRQHandler

/* bxCAN filter bank count (F103 has 14) */
#define CAN_FILTER_BANK_COUNT       14

/*============================================================================
 * Communication Interface Configuration
 *============================================================================*/

/* --- USART1 (default communication channel) --- */
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

/*============================================================================
 * ADC Configuration (Optional)
 *============================================================================*/
#define ADC_INSTANCE                 ADC1
#define ADC_SAMPLING_RATE_MAX_HZ     1000000UL   /* 1 Msps for F103 */
#define ADC_RESOLUTION_BITS          12
#define ADC_CHANNEL_COUNT            10
#define ADC_PERIPH_CLK_ENABLE()      __HAL_RCC_ADC1_CLK_ENABLE()
#define ADC_GPIO_CLK_ENABLE()        __HAL_RCC_GPIOA_CLK_ENABLE()
#define ADC_CAN_MONITOR_CHANNEL      ADC_CHANNEL_0   /* PA0 as CAN bus monitor input */

/*============================================================================
 * GPIO / Debug LED
 *============================================================================*/
#define DEBUG_LED_PORT               GPIOC
#define DEBUG_LED_PIN                GPIO_PIN_13
#define DEBUG_LED_CLK_ENABLE()       __HAL_RCC_GPIOC_CLK_ENABLE()

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
#define CAN_RX_FIFO_SIZE             64
#define CAN_TX_FIFO_SIZE             32
#define COMM_RX_BUF_SIZE             256
#define COMM_TX_BUF_SIZE             512
#define ADC_SAMPLE_BUF_SIZE          1024
#define PROTOCOL_FRAME_MAX_SIZE      512

#ifdef __cplusplus
}
#endif

#endif /* STM32F103_CONFIG_H */
