import os
import time
import re
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import ddddocr
from dotenv import load_dotenv
load_dotenv()  # lê o .env local (não vai para o GitHub)

# ================= CONFIGURAÇÕES =================
URL_SEFAZ = "https://efisc.sefaz.ba.gov.br/efiscalizacao/jsp/login/login.jsf"
ARQUIVO_CSV = "CONSULTA DTE.csv" 

# Diretório exato (A subpasta da data é criada automaticamente dentro dele)
DIRETORIO_BASE = os.getenv("DIRETORIO_BASE")

# CONFIGURAÇÃO DE ANO DA PESQUISA
ANOS_PESQUISA = ["2025", "2026"]
# ==================================================

def iniciar_navegador():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new") 
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    # Oculta as mensagens de erro feias do próprio Chrome/Selenium
    options.add_argument("--log-level=3") 
    options.add_argument("--silent")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    servico = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=servico, options=options)

def criar_pasta_do_dia():
    data_atual = datetime.now().strftime("%d-%m-%Y")
    caminho_pasta = os.path.join(DIRETORIO_BASE, data_atual)
    os.makedirs(caminho_pasta, exist_ok=True)
    return caminho_pasta

def quebrar_captcha(driver, wait, ocr):
    try:
        img_element = wait.until(EC.presence_of_element_located((By.XPATH, '//img[contains(@src, "captcha")]')))
        link_imagem = img_element.get_attribute('src')
        
        janela_principal = driver.current_window_handle
        driver.execute_script(f"window.open('{link_imagem}', '_blank');")
        time.sleep(1.5) 
        
        for handle in driver.window_handles:
            if handle != janela_principal:
                driver.switch_to.window(handle)
                break
                
        img_na_nova_aba = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'img')))
        img_na_nova_aba.screenshot('captcha_temp.png')
        
        driver.close()
        driver.switch_to.window(janela_principal)
        
        with open('captcha_temp.png', 'rb') as f:
            img_bytes = f.read()
            
        texto_sujo = ocr.classification(img_bytes)
        texto_limpo = re.sub(r'[^A-Za-z0-9]', '', texto_sujo)
        return texto_limpo
    except Exception as e:
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        return ""

def processar_empresas():
    print("A iniciar rotina DTE SEFAZ-BA (Espera Inteligente + Regra 15 Dias)...")
    
    ocr = ddddocr.DdddOcr()
    pasta_destino = criar_pasta_do_dia()
    data_hoje = datetime.now()
    
    try:
        df = pd.read_csv(ARQUIVO_CSV, dtype=str)
        df.fillna('', inplace=True)
    except FileNotFoundError:
        print(f"Erro: O ficheiro '{ARQUIVO_CSV}' não foi encontrado.")
        return

    for index, row in df.iterrows():
        login = str(row.get('Login', '')).strip()
        senha = str(row.get('Senha', '')).strip()
        cnpj = str(row.get('CNPJ', 'SEM_CNPJ'))
        empresa_nome = str(row.get('Empresa', 'Desconhecida'))
        
        empresa_limpa = re.sub(r'[\\/*?:"<>|]', "", empresa_nome).strip()

        if login == '' or login.upper() == 'NÃO TEM' or senha == '':
            continue

        print(f"\n[{index+1}] A processar: {empresa_nome} | CNPJ: {cnpj}")
        
        driver = iniciar_navegador()
        
        # Aumentado o tempo limite global para 15 segundos devido à lentidão da SEFAZ
        wait = WebDriverWait(driver, 15) 
        
        sucesso_login = False
        
        try:
            for tentativa in range(1, 8):
                try:
                    driver.delete_all_cookies()
                    driver.get(URL_SEFAZ)
                    time.sleep(2)
                    
                    campo_login = wait.until(EC.element_to_be_clickable((By.XPATH, '//input[@id="frmLogin:txtLogin"]')))
                    campo_login.clear()
                    campo_login.send_keys(login)
                    
                    campo_senha = driver.find_element(By.XPATH, '//input[@type="password" or @name="frmLogin:j_id17"]')
                    campo_senha.clear()
                    campo_senha.send_keys(senha)
                    
                    texto_captcha = quebrar_captcha(driver, wait, ocr)
                    if len(texto_captcha) != 5:
                        raise Exception(f"A IA leu {len(texto_captcha)} caracteres ('{texto_captcha}').")
                        
                    input_captcha = driver.find_element(By.XPATH, '//input[@id="frmLogin:captchaInput"]')
                    input_captcha.clear()
                    input_captcha.send_keys(texto_captcha)
                    
                    driver.find_element(By.XPATH, '//a[@id="frmLogin:btnEntrar"]').click()
                    
                    try:
                        alert = WebDriverWait(driver, 2).until(EC.alert_is_present())
                        erro_alert = alert.text
                        alert.accept()
                        raise Exception(f"Aviso da SEFAZ: {erro_alert}")
                    except:
                        pass
                    
                    wait.until(EC.element_to_be_clickable((By.XPATH, '//a[contains(., "Mensagens DTE")]')))
                    sucesso_login = True
                    print(f"  [✓] Login efetuado com sucesso na tentativa {tentativa}!")
                    break 
                except Exception as erro_loop:
                    # Tratamento para limpar o log e não poluir a tela com Stacktraces
                    erro_str = str(erro_loop).split('\n')[0]
                    if "TimeoutException" in str(type(erro_loop)):
                        erro_str = "Tempo esgotado aguardando carregamento do site."
                    print(f"  [X] Falha na tentativa {tentativa}. Motivo: {erro_str}")
                    time.sleep(1)
            
            if not sucesso_login:
                print(f"  [X] Limite de tentativas excedido.")
                df.at[index, 'Situação'] = 'ERRO LOGIN'
                df.at[index, 'Observação'] = 'Falha no acesso após 7 tentativas.'
                driver.save_screenshot(os.path.join(pasta_destino, f'ERRO LOGIN - {empresa_limpa}.png'))
                continue 
                
            # ================= ENTRAR NA CAIXA DE MENSAGENS =================
            wait.until(EC.element_to_be_clickable((By.XPATH, '//a[contains(., "Mensagens DTE")]'))).click()
            wait.until(EC.element_to_be_clickable((By.XPATH, '//a[contains(@href, "caixaMensagem.jsf") or contains(., "Ir para Caixa de Entrada")]'))).click()
            
            janela_principal = driver.current_window_handle
            
            print("  [Detetive] Aguardando a tabela de mensagens carregar...")
            
            # ESPERA INTELIGENTE: O robô aguarda até 20 segundos para a tabela ou a mensagem de "vazia" aparecer na tela
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: len(d.find_elements(By.XPATH, '//tr[contains(@id, "form:tableDTE:")]')) > 0 or \
                              len(d.find_elements(By.XPATH, '//div[contains(text(), "Não há mensagens na sua Caixa de Entrada")]')) > 0
                )
            except:
                print("  [Aviso] O site demorou muito a responder. Tentando ler a tabela mesmo assim...")
                
            time.sleep(2) # Respiro extra para o JavaScript da SEFAZ assentar
            
            caixa_vazia = driver.find_elements(By.XPATH, '//div[contains(text(), "Não há mensagens na sua Caixa de Entrada")]')
            if len(caixa_vazia) > 0:
                caminho_vazio = os.path.join(pasta_destino, f'REGULAR - {empresa_limpa}.png')
                driver.save_screenshot(caminho_vazio)
                df.at[index, 'Situação'] = 'REGULAR'
                df.at[index, 'Observação'] = caixa_vazia[0].text
                print(f"  [✓] REGULAR - Caixa vazia confirmada. Print salvo.")
                continue

            # ================= DETETIVE DE TABELA E FILTRO =================
            linhas_tabela = driver.find_elements(By.XPATH, '//tr[contains(@id, "form:tableDTE:")]')
            mensagens_alvo_encontradas = []
            
            print(f"  [Detetive] {len(linhas_tabela)} mensagens encontradas na tela. Processando dados...")
            
            for linha in linhas_tabela:
                celulas = linha.find_elements(By.TAG_NAME, 'td')
                texto_linha = linha.text.strip().upper()
                
                ano_mensagem = None
                data_mensagem = "Data não identificada"
                data_obj = None
                
                for celula in celulas:
                    match_data = re.search(r'(\d{2})/(\d{2})/(\d{4})', celula.text)
                    if match_data:
                        data_mensagem = celula.text.strip()
                        ano_mensagem = match_data.group(3)
                        data_obj = datetime.strptime(data_mensagem, "%d/%m/%Y")
                        break
                
                if not ano_mensagem or ano_mensagem not in ANOS_PESQUISA:
                    continue
                
                dias_passados = 999
                if data_obj:
                    dias_passados = (data_hoje - data_obj).days

                # 1ª REGRA: IRREGULARIDADE (Até 15 dias + Cobrança/Débito)
                if dias_passados <= 15:
                    if "COBRANÇA" in texto_linha or "COBRANCA" in texto_linha or "DÉBITO" in texto_linha or "DEBITO" in texto_linha:
                        mensagens_alvo_encontradas.append((linha, data_mensagem, "IRREGULAR"))
                        continue

                # 2ª REGRA: MENSAGEM NOVA GENÉRICA
                esta_nao_lida = False
                if "NÃO LIDA" in texto_linha or "NÃO LIDO" in texto_linha:
                    esta_nao_lida = True
                
                if linha.find_elements(By.XPATH, './/b | .//strong'):
                    esta_nao_lida = True
                    
                style_linha = linha.get_attribute("style") or ""
                if "bold" in style_linha.lower():
                    esta_nao_lida = True
                
                for c in celulas:
                    if c.text.strip() == "-" or c.text.strip() == "":
                        if c.get_attribute("id") and "j_id" in c.get_attribute("id"):
                            esta_nao_lida = True

                if esta_nao_lida:
                    mensagens_alvo_encontradas.append((linha, data_mensagem, "MENSAGEM NOVA"))

            # ================= DECISÃO E PRINTS =================
            qtd_mensagens = len(mensagens_alvo_encontradas)
            
            if qtd_mensagens > 0:
                tem_irregular = any(tipo == "IRREGULAR" for _, _, tipo in mensagens_alvo_encontradas)
                status_final = "IRREGULAR" if tem_irregular else "MENSAGEM NOVA"
                
                print(f"  [!] Alerta! Mensagens relevantes detectadas. Status: {status_final}")
                
                if qtd_mensagens > 1:
                    print_lista = os.path.join(pasta_destino, f'ATENCAO MULTIPLAS MENSAGENS - {empresa_limpa}.png')
                    driver.save_screenshot(print_lista)

                primeira_linha = mensagens_alvo_encontradas[0][0]
                data_primeira = mensagens_alvo_encontradas[0][1]

                lupa = primeira_linha.find_element(By.XPATH, './/a[contains(@title, "Visualizar") or contains(@class, "lupa") or @href="#"]')
                lupa.click()
                time.sleep(3)
                
                if len(driver.window_handles) > 1:
                    for handle in driver.window_handles:
                        if handle != janela_principal:
                            driver.switch_to.window(handle)
                            break
                time.sleep(2)
                
                caminho_print = os.path.join(pasta_destino, f'{status_final} - {empresa_limpa}.png')
                driver.save_screenshot(caminho_print)
                
                try:
                    assunto_elemento = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="assunto_mensagem"] | //h2 | //div[contains(@class, "assunto")]')))
                    teor_mensagem = assunto_elemento.text.strip()
                except:
                    teor_mensagem = "Verificado no print"

                if status_final == "IRREGULAR":
                    obs_final = f"🚨 IRREGULARIDADE! Detectada cobrança (nos últimos 15 dias). Data: {data_primeira}. Teor: {teor_mensagem}"
                elif qtd_mensagens > 1:
                    obs_final = f"ATENÇÃO: {qtd_mensagens} mensagens novas! Lida a 1ª de {data_primeira}. Teor: {teor_mensagem}"
                else:
                    obs_final = f"Teve mensagem não lida de Data: {data_primeira}. Teor: {teor_mensagem}"

                df.at[index, 'Situação'] = status_final
                df.at[index, 'Observação'] = obs_final
                print(f"  [!] {status_final} processada. Print do conteúdo salvo com sucesso.")
                
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(janela_principal)
            else:
                caminho_regular = os.path.join(pasta_destino, f'REGULAR - {empresa_limpa}.png')
                driver.save_screenshot(caminho_regular)
                
                df.at[index, 'Situação'] = 'REGULAR'
                df.at[index, 'Observação'] = f"Sem cobranças (15 dias) ou mensagens não lidas nos anos {ANOS_PESQUISA}."
                print(f"  [✓] REGULAR - Nenhuma mensagem pendente. Print da tabela salvo.")
                
        except Exception as e:
            erro_fatal = str(e).split('\n')[0]
            print(f"  [X] Erro Crítico no processamento: {erro_fatal}")
            driver.save_screenshot(os.path.join(pasta_destino, f'ERRO FATAL - {empresa_limpa}.png'))
            df.at[index, 'Situação'] = 'ERRO FATAL'
            df.at[index, 'Observação'] = 'Verificar print de erro fatal.'
            
        finally:
            try:
                driver.quit()
            except:
                pass
            if os.path.exists('captcha_temp.png'):
                os.remove('captcha_temp.png')
            
            df.to_csv('Resultado_' + ARQUIVO_CSV, index=False)

    print("\n=======================================================")
    print("Processamento concluído com sucesso e planilha salva!")
    print("=======================================================")

if __name__ == "__main__":
    processar_empresas()