import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# Inicializa o cliente da OpenAI buscando a chave das variáveis de ambiente
# (Você vai cadastrar a OPENAI_API_KEY lá na Render)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def limpar_html_para_ia(html_puro):
    """Remove excessos do HTML para economizar tokens e dinheiro nos seus testes"""
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
        # 1. Simula navegador para evitar o bloqueio 403 padrão
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }
        
        resposta_site = requests.get(url, headers=headers, timeout=15)
        
        if resposta_site.status_code != 200:
            return jsonify({
                "erro": False,
                "score": 0,
                "nome": nome_opcional or "Erro de Acesso",
                "detalhes": f"O site bloqueou o acesso direto do robô (Código: {resposta_site.status_code}).",
                "valor_atual": seu_preco,
                "valor_concorrente": "Não localizado"
            })

        # 2. Limpa o conteúdo
        conteudo_limpo = limpar_html_para_ia(resposta_site.text)

        # 3. Chama o ChatGPT (modelo gpt-4o-mini para máxima economia)
        prompt = f"""
        Analise o texto estruturado de uma página de produto e capture o preço real de venda.
        Ignore valores antigos riscados ou preços de parcelamento longo se houver valor à vista.
        Se encontrar o nome do produto no texto, capture também.

        Texto da página:
        {conteudo_limpo}

        Responda rigorosamente no formato JSON abaixo, sem marcações markdown como ```json ou textos adicionais:
        {{
            "nome": "Nome do produto",
            "preco_alvo": 159.90,
            "detalhes": "Condição ou observação sobre o preço"
        }}
        Se não encontrar nenhum preço viável, retorne 0 em preco_alvo.
        """

        resposta_ia = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um extrator de dados preciso que responde apenas em JSON puro."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        # 4. Trata o retorno do ChatGPT
        texto_json = resposta_ia.choices[0].message.content.strip()
        
        import json
        dados_ia = json.loads(texto_json)

        preco_concorrente = dados_ia.get("preco_alvo", 0)
        nome_produto = nome_opcional or dados_ia.get("nome", "Produto em Monitoramento")
        detalhes = dados_ia.get("detalhes", "Extraído com sucesso via Inteligência Semântica.")

        # 5. Cálculo básico de arbitragem para o Score
        try:
            v_seu = float(seu_preco)
            v_conc = float(preco_concorrente)
            score = int(((v_conc - v_seu) / v_conc) * 100) if v_conc > 0 else 0
            score = max(0, min(100, score))
        except:
            score = 0

        return jsonify({
            "erro": False,
            "score": score,
            "nome": nome_produto,
            "detalhes": detalhes,
            "valor_atual": v_seu,
            "valor_concorrente": v_concorrente
        })

    except Exception as e:
        print(f"Erro: {str(e)}")
        return jsonify({"erro": True, "mensagem": f"Erro interno: {str(e)}"}), 500