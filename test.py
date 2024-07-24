import math
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from chromedriver_autoinstaller import install as chrome_driver_install



BINANCE_URL = "https://p2p.binance.com/en/trade/sell/USDT?fiat=ARS&payment=all-payments"
DOLARHOY_URL = "https://dolarhoy.com/"
SHORT_TIMEOUT = 1.5
DRIVER_PATH = '../chromedriver.exe'
RDA_COMISSION = 0.85
BINANCE_COMISSION_TO_SUBSTRACT = 0.96
ONLY_PAYO = False

def main_function():
    
    driver = driver_initialization()
    driver.maximize_window()
    driver.get(DOLARHOY_URL)
    
    RDA_COMISSION = float(input("Enter the commission to use in this execution (0.85 is the minimum): "))
    ONLY_PAYO = bool(input("Only Payoneer text? (YES/NO): "))
    
    buy_element = driver.find_element(By.CLASS_NAME, "compra").text
    sell_element = driver.find_element(By.CLASS_NAME, "venta").text
    
    driver.get(BINANCE_URL)
    try:
        time.sleep(4)
        driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
        print("Accepting coockies.")
    except:
        print("Coockies button not detected.")
    
    cotizations = driver.find_elements(By.XPATH, "//*[contains(@class, 'headline5') and contains(@class, 'mr-4xs') and contains(@class, 'text-primaryText')]")
    cotization_text1 = cotizations[-1].text
    cotization_text2 = cotizations[0].text
    cotization_text1 = cotization_text1.replace(',', '')
    cotization_text2 = cotization_text2.replace(',', '')
    cotization1 = float(cotization_text1)
    cotization2 = float(cotization_text2)
    
    print("\r")
    
    print(f"Dolar Blue {sell_element}")
    print(f"Dolar Blue {buy_element}")
    
    print("\r")
    print("\r")
    
    print("COTIZACION MAS ALTA BINANCE: " + str(cotization2))
    print("COTIZACION MAS BAJA BINANCE: " + str(cotization1))
    
    internal_cotization = (((cotization2-cotization1)/2)+cotization1) * BINANCE_COMISSION_TO_SUBSTRACT
    internal_cotization = round(internal_cotization, 2)
    
    print(f"Valor real que me queda por Wise/Payoneer: {internal_cotization}")
    cotization1 = math.floor(cotization1 * RDA_COMISSION)
    print("COTIZACION FINAL CON COMISION (APLICADA A LA MAS BAJA): " + str(cotization1))
    
    print("\r")
    print("\r")
    
    
    if not ONLY_PAYO:
        print("Estamos cambiando como minimo 150 usd.")
        print("Te paso la ultima cotización del día! . Trabajamos también los fines de semana, 24 HS disponibles!")
        print("También compramos saldo BINANCE! ")
        print("\r")
        print(str((cotization1+4)) + " menos de 600 USD Binance")
        print(str((cotization1+5)) + " mas de 600 USD Binance")
        print("\r")
        print(str((cotization1)) + " menos de 400 USD Payoneer")
        print(str((cotization1+1)) + " entre 400 y 800 USD Payoneer")
        print(str((cotization1+2)) + " mas de 800 USD Payoneer")
        print("\r")
        print(str((cotization1+2)) + " menos de 400 USD Wise/TransferWise")
        print(str((cotization1+3)) + " entre 400 y 800 USD Wise/TransferWise")
        print(str((cotization1+4)) + " mas de 800 USD Wise/TransferWise")
    else:
        print("Estamos cambiando como minimo 150 usd.")
        print("Te paso la ultima cotización del día! . Trabajamos también los fines de semana, 24 HS disponibles!")
        print("También compramos saldo BINANCE! ")
        print("\r")
        print(str((cotization1)) + " menos de 400 USD Payoneer")
        print(str((cotization1+1)) + " entre 400 y 800 USD Payoneer")
        print(str((cotization1+2)) + " mas de 800 USD Payoneer")
    
        
    driver.quit()   
            
    
def driver_initialization():    
        chrome_driver_install()
        
        coptions = webdriver.ChromeOptions()
        coptions.add_argument('--ignore-certificate-errors')
        coptions.add_argument('--disable-extensions')
        coptions.add_argument('--headless')
        coptions.add_argument('--disable-gpu')
        coptions.add_argument('--no-sandbox')
        coptions.add_argument('--disable-dev-shm-usage')
        coptions.add_argument("--log-level=3")
        
        service = ChromeService(log_path='NUL')

        return webdriver.Chrome(service=service, options=coptions)
    

    
if __name__ == "__main__":
    main_function()