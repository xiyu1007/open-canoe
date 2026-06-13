/**
 * @file    main.c
 * @brief   Open-Canoe firmware entry point and main loop.
 *
 * Startup:
 *   1. HAL_Init → SystemClock_Config → SysTick re-init
 *   2. GPIO, Timer, Comm init
 *   3. Send device heartbeat
 *   4. Enter main loop → process incoming protocol frames
 *
 * CAN and ADC are NOT started automatically — wait for App commands.
 */

#include "device_config.h"
#include <string.h>

#if defined(STM32F103xB)
#include "stm32f1xx_hal.h"
#elif defined(STM32F407xx)
#include "stm32f4xx_hal.h"
#endif

#include "can_api.h"
#include "adc_api.h"
#include "comm_api.h"
#include "device_api.h"
#include "protocol.h"

/*============================================================================
 * External Functions
 *============================================================================*/

extern int  protocol_process_byte(uint8_t byte);
extern void protocol_process_buffer(const uint8_t *data, uint16_t length);
extern void protocol_send_can_frame(const can_frame_t *frame);
extern void protocol_send_adc_data(const adc_sample_data_t *data);
extern int  protocol_send_heartbeat(void);

/*============================================================================
 * Private Functions
 *============================================================================*/

static void SystemClock_Config(void);
static void GPIO_Init(void);
static void TimestampTimer_Init(void);
static void Error_Handler(void);

/*============================================================================
 * Callbacks
 *============================================================================*/

static void can_rx_callback(const can_frame_t *frame)
{
    protocol_send_can_frame(frame);
}

static void adc_data_callback(const adc_sample_data_t *data)
{
    protocol_send_adc_data(data);
}

/*============================================================================
 * Main Entry
 *============================================================================*/

int main(void)
{
    /*---- Step 1: HAL Init ----*/
    HAL_Init();

    /*---- Step 2: System Clock ----*/
    SystemClock_Config();

    /* Re-init SysTick after clock change */
    HAL_SYSTICK_Config(HAL_RCC_GetHCLKFreq() / 1000U);
    HAL_SYSTICK_CLKSourceConfig(SYSTICK_CLKSOURCE_HCLK);

    /*---- Step 3: GPIO ----*/
    GPIO_Init();

    /*---- Step 4: Timestamp Timer ----*/
    TimestampTimer_Init();

    /*---- Step 5: Communication Interface ----*/
    comm_config_t comm_cfg;
    comm_cfg.type     = COMM_IF_USART;
    comm_cfg.baudrate = COMM_USART_BAUDRATE;

    if (comm_init(&comm_cfg) != COMM_OK) {
        Error_Handler();
    }

    /*---- Step 6: Send Device Heartbeat ----*/
    protocol_send_heartbeat();

    /*---- Step 7: Register CAN and ADC callbacks ----*/
    can_register_rx_callback(0, can_rx_callback);
#if CAN_INSTANCE_COUNT > 1
    can_register_rx_callback(1, can_rx_callback);
#endif
    adc_register_data_callback(adc_data_callback);

    /*---- Step 8: Main Loop ----*/
    while (1)
    {
        uint8_t byte_buf[64];
        uint16_t recv_len;

        /* Process incoming protocol commands */
        comm_status_t ret = comm_receive(byte_buf, sizeof(byte_buf), &recv_len, 0);
        if (ret == COMM_OK && recv_len > 0) {
            protocol_process_buffer(byte_buf, recv_len);
        }

        /* Poll CAN RX FIFO for received frames (loopback or real bus).
         * Interrupt-based reception is the primary path, but polling
         * catches frames if the IRQ was missed or shared-IRQ conflicts. */
        for (uint8_t ch = 0; ch < can_get_channel_count(); ch++) {
            if (can_is_initialized(ch)) {
                can_frame_t frame;
                if (can_receive_frame(ch, &frame, 0) == CAN_OK) {
                    protocol_send_can_frame(&frame);
                }
            }
        }
    }
}

/*============================================================================
 * System Clock Configuration
 *============================================================================*/

static void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

#if defined(STM32F103xB)
    /* Try HSI first (more compatible). HSI 8MHz /2 * PLL16 = 64MHz.
     * APB1 = 32MHz, APB2 = 64MHz. CAN timing adjusted accordingly. */
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL16;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
        Error_Handler();

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
        Error_Handler();

#elif defined(STM32F407xx)
    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM = 24;
    RCC_OscInitStruct.PLL.PLLN = 336;
    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ = 4;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
        Error_Handler();

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
        Error_Handler();

    __HAL_RCC_SYSCFG_CLK_ENABLE();
#endif
}

/*============================================================================
 * GPIO Initialization
 *============================================================================*/

static void GPIO_Init(void)
{
    DEBUG_LED_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_OUTPUT_PP;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    gpio.Pin   = DEBUG_LED_PIN;
    HAL_GPIO_Init(DEBUG_LED_PORT, &gpio);

    HAL_GPIO_WritePin(DEBUG_LED_PORT, DEBUG_LED_PIN, GPIO_PIN_RESET);
}

/*============================================================================
 * Timestamp Timer (TIM2) — free-running 1 MHz counter
 *============================================================================*/

static void TimestampTimer_Init(void)
{
    TIMESTAMP_TIMER_CLK_ENABLE();
    TIMESTAMP_TIMER->PSC = (APB1_CLOCK_HZ * 2 / TIMESTAMP_TIMER_CLK_HZ) - 1;
    TIMESTAMP_TIMER->ARR = 0xFFFFFFFF;
    TIMESTAMP_TIMER->CR1 = TIM_CR1_CEN;
}

/*============================================================================
 * SysTick Handler
 *============================================================================*/

void SysTick_Handler(void)
{
    HAL_IncTick();
    extern void device_tick_ms(void);
    device_tick_ms();
}

/*============================================================================
 * Error Handler
 *============================================================================*/

static void Error_Handler(void)
{
    __disable_irq();
    while (1) {
        HAL_GPIO_TogglePin(DEBUG_LED_PORT, DEBUG_LED_PIN);
        for (volatile uint32_t i = 0; i < 500000; i++) { }
    }
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
    (void)file;
    (void)line;
    Error_Handler();
}
#endif
