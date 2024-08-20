from selenium import webdriver
from selenium.webdriver.common.by import By
from time import sleep

from credentials import LOGIN,PASSWORD
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option('useAutomationExtension', False)
chrome_options.add_argument("window-size=1200x600")
driver = webdriver.Chrome(options=chrome_options)
driver.get("https://kwork.ru/")


def open_all_chats():
   all_chats_button = driver.find_element(By.XPATH,'//*[@id="body"]/div[7]/div[1]/div[1]/div/div[2]/div[3]/div[3]/div[1]/a')
   all_chats_button.click()
   sleep(3)
   
   # Используйте JavaScript для добавления MutationObserver на элемент
   driver.execute_script("""
   var targetNode = document.evaluate('//*[@id="app-chat-list"]/div/div[2]/div/div[3]/ul', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    var observer = new MutationObserver(function(mutationsList, observer) {
        for(var mutation of mutationsList) {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.classList && node.classList.contains('chat__list-item')) {
                        console.log('A new chat list item has been added.');
                        node.click()
                    }
                });
            }
        }
    });
    observer.observe(targetNode, { attributes: true, childList: true, subtree: true });
    console.log('Observer has been set.');
""")

def login():
   # try:
      login_input = driver.find_element(By.XPATH,'//*[@id="form-login-page"]/div[1]/div/input')
      password_input = driver.find_element(By.XPATH,'//*[@id="form-login-page"]/div[2]/div/input')
      print(LOGIN,PASSWORD)

      # zapomnit_menu = driver.find_element(By.XPath,'/html/body/div[2]/div/div[1]/div/div/div[2]/div/div[1]/form/div[4]/div/input')
      login_input.send_keys(LOGIN)
      password_input.send_keys(PASSWORD)
      sleep(5)

      login_button = driver.find_element(By.XPATH,'//*[@id="form-login-page"]/button')
      login_button.click()
     
   # except:
   #    print('----Не удалось залогиниться----')
def start():
   driver.implicitly_wait(2)
   login_modal_button_open =driver.find_element(By.XPATH, '//*[@id="app-header-select"]/li[1]/a')
   login_modal_button_open.click()
   sleep(3)
   login()


if __name__ == '__main__':
   start()