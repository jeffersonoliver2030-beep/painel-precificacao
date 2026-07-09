import os
import re
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import cloudscraper
from bs4 import BeautifulSoup
import google.generativeai as genai  # Biblioteca oficial do Gemini

app = Flask(__name__)
CORS(app)

# Configura a chave do Gemini buscando de forma segura do ambiente
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Inicializa o modelo usando a nomenclatura estável atual
model = genai.GenerativeModel('gemini-2.5-flash')

def limpar_html_para_ia(html_puro):
    """Remove o excesso de código do site para economizar seus tokens no Gemini"""
    soup = BeautifulSoup(html_puro, 'html.parser')
    for elemento in soup(["script", "style", "nav", "footer", "iframe", "header"]):
        elemento.decompose()
    return re.sub(r'\s+', ' ', soup.get_text())[:8000]

@app.route('/analisar-alvo', methods=['POST'])
def analisar_alvo():
    dados = request.get_json()
    url = dados.get('url')
    seu_preco = dados.get('seu_preco', '0.00')
    nome_opcional = dados.get('nome', '')

    if not url:
        return jsonify({"erro": True, "mensagem": "URL não fornecida"}), 400

   try:
     # Cria um raspador avançado que pula proteções de e-commerce
     scraper = cloudscraper.create_scraper()
     resposta_site = scraper.get(url, timeout=15)

     # LINHAS DE RASTREAMENTO (PRINT)
     print("--- DEBUG RASPAGEM ---")
     print(f"Status Code do Site: {resposta_site.status_code}")
     print(f"Tamanho do HTML baixado: {len(resposta_site.text)} caracteres")
     print(f"Começo do texto capturado: {resposta_site.text[:500]}")
     print("----------------------")
        
        if resposta_site.status_code != 200:
            return jsonify({
                "erro": False,
                "score": 0,
                "nome": nome_opcional or "Erro de Acesso ao Site",
                "detalhes": f"O site respondeu com código de erro: {resposta_site.status_code}.",
                "valor_atual": seu_preco,
                "valor_concorrente": 0
            })

        # 2. Limpa o excesso de código da página usando a função auxiliar
        conteudo_limpo = limpar_html_para_ia(resposta_site.text)

        # 3. Prompt estruturado para forçar o Gemini a responder em JSON estável
        prompt = f"""
        Você é um analisador e extrator de dados de e-commerce ultra preciso.
        Analise o fragmento de texto de uma página de produto abaixo e extraia com exatidão o preço real atual de venda do produto e o nome dele.
        Ignore preços antigos riscados ou valores de parcelamento muito longos com juros caso exista preço à vista.

        Texto extraído da página:
        {conteudo_limpo}

        Responda obrigatoriamente apenas no formato JSON abaixo, sem blocos markdown (como ```json) ou textos adicionais:
        {{
            "nome": "Nome completo do produto encontrado",
            "preco_alvo": 159.90,
            "detalhes": "Breve comentário sobre condições encontradas"
        }}
        Se nenhum preço válido for localizado, retorne 0 no campo preco_alvo.
        """

        # 4. Aciona o modelo de IA
        resposta_ia = model.generate_content(prompt)
        texto_json = resposta_ia.text.strip()
        
        # Remove eventuais marcações de markdown do JSON retornadas pela IA
        texto_json = re.sub(r'```json\s*|```', '', texto_json)
        dados_ia = json.loads(texto_json)

        preco_concorrente = dados_ia.get("preco_alvo", 0)
        nome_produto = nome_opcional or dados_ia.get("nome", "Produto em Monitoramento")
        detalhes = dados_ia.get("detalhes", "Análise realizada com sucesso via IA Semântica.")

        # 5. Processamento dos preços e geração de score comparativo
        try:
            v_seu = float(str(seu_preco).replace(',', '.'))
            v_conc = float(preco_concorrente)
            
            # Cálculo de diferença percentual
            if v_conc > 0:
                score = int(((v_conc - v_seu) / v_conc) * 100)
                score = max(0, min(100, score))
            else:
                score = 0
                detalhes = "Preço do concorrente não pôde ser identificado no site."
        except Exception as err_calc:
            v_seu = 0.0
            v_conc = 0.0
            score = 0
            detalhes = f"Falha ao converter formatos de moeda: {str(err_calc)}"

        return jsonify({
            "erro": False,
            "score": score,
            "nome": nome_produto,
            "detalhes": detalhes,
            "valor_atual": v_seu,
            "valor_concorrente": v_conc
        })

    except Exception as e:
        print(f"Erro interno: {str(e)}")
        return jsonify({"erro": True, "mensagem": f"Erro interno no processador: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
