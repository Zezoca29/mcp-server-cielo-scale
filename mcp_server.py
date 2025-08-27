from fastmcp import FastMCP
import requests
import subprocess
import json
import time
import sys
import os
from typing import Dict, Any

mcp = FastMCP("mcp-orchestrator")

# Cache para resources MCP
last_analyses = []
last_prompts = []

def _dispatch_analyze(language: str, code: str) -> Dict[str, Any]:
    """Despacha análise para o runtime apropriado baseado na linguagem"""
    lang = language.lower()
    
    try:
        if lang == "java":
            print(f"[INFO] Dispatching Java analysis to Spring Boot service...", file=sys.stderr)
            r = requests.post(
                "http://localhost:8080/analyze", 
                json={"code": code}, 
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            r.raise_for_status()
            return r.json()
            
        elif lang == "python":
            print(f"[INFO] Dispatching Python analysis to local analyzer...", file=sys.stderr)
            analyzer_path = os.path.join("runtimes", "python", "analyzer.py")
            if not os.path.exists(analyzer_path):
                return {"error": f"Python analyzer not found at {analyzer_path}"}
                
            p = subprocess.run(
                [sys.executable, analyzer_path],
                input=code.encode("utf-8"),
                capture_output=True, 
                timeout=10
            )
            
            if p.returncode != 0:
                return {"error": f"Python analyzer failed: {p.stderr.decode()}"}
                
            result = p.stdout.decode().strip()
            if not result:
                return {"error": "Python analyzer returned empty result"}
                
            return json.loads(result)
            
        elif lang in ["ts", "typescript", "js", "javascript"]:
            print(f"[INFO] Dispatching TypeScript/JS analysis to Node analyzer...", file=sys.stderr)
            analyzer_path = os.path.join("runtimes", "ts", "analyzer.js")
            if not os.path.exists(analyzer_path):
                return {"error": f"TypeScript analyzer not found at {analyzer_path}"}
                
            p = subprocess.run(
                ["node", analyzer_path],
                input=code.encode("utf-8"),
                capture_output=True, 
                timeout=10
            )
            
            if p.returncode != 0:
                return {"error": f"TypeScript analyzer failed: {p.stderr.decode()}"}
                
            result = p.stdout.decode().strip()
            if not result:
                return {"error": "TypeScript analyzer returned empty result"}
                
            return json.loads(result)
            
        else:
            return {"error": f"Unsupported language: {language}. Supported: java, python, typescript/js"}
            
    except requests.RequestException as e:
        return {"error": f"HTTP request failed: {str(e)}"}
    except subprocess.TimeoutExpired:
        return {"error": f"Analysis timeout for {language}"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON response from {language} analyzer: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error in {language} analysis: {str(e)}"}

@mcp.tool()
def analyze_function(language: str, code: str) -> Dict[str, Any]:
    """
    Analisa estaticamente uma função em Java, Python ou TypeScript
    
    Args:
        language: Linguagem do código (java, python, typescript, js)
        code: Código fonte da função
        
    Returns:
        Análise estrutural da função com inputs, outputs, complexidade, branches
    """
    print(f"[INFO] Starting analysis for {language} code...", file=sys.stderr)
    
    result = _dispatch_analyze(language, code)
    
    # Normalização e defaults para garantir contrato consistente
    normalized = {
        "language": language,
        "functions": result.get("functions", []),
        "inputs": result.get("inputs", []),
        "outputs": result.get("outputs", []),
        "complexity": result.get("complexity", 0),
        "branches": result.get("branches", 0),
        "side_effects": result.get("side_effects", []),
        "raw": result
    }
    
    # Cache para resource
    global last_analyses
    last_analyses.append({
        "timestamp": time.time(),
        "language": language,
        "result": normalized
    })
    # Manter apenas os últimos 10
    last_analyses = last_analyses[-10:]
    
    print(f"[INFO] Analysis completed. Functions: {len(normalized['functions'])}, Branches: {normalized['branches']}", file=sys.stderr)
    return normalized

@mcp.tool()
def summarize_flow(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resume o fluxo de execução baseado na análise estática
    
    Args:
        summary: Resultado da análise de analyze_function
        
    Returns:
        Resumo estruturado com caminhos, casos limite e matriz IO
    """
    print("[INFO] Summarizing execution flow...", file=sys.stderr)
    
    # Extrair métricas
    complexity = summary.get("complexity", 0)
    branches = summary.get("branches", 0)
    functions = summary.get("functions", [])
    inputs = summary.get("inputs", [])
    outputs = summary.get("outputs", [])
    side_effects = summary.get("side_effects", [])
    
    # Gerar caminhos baseados em branches
    num_paths = max(1, branches) if branches > 0 else 1
    key_paths = [f"main_path_{i+1}" for i in range(num_paths)]
    
    # Casos limite padrão + específicos baseados em side effects
    edge_cases = [
        "null/None inputs",
        "empty collections", 
        "boundary numbers (0, -1, max)",
        "exception paths"
    ]
    
    if side_effects:
        edge_cases.extend([
            "IO failures",
            "network timeouts",
            "resource unavailability"
        ])
    
    if complexity > 5:
        edge_cases.append("high complexity paths")
    
    # Matriz IO para teste
    io_matrix = []
    if inputs:
        io_matrix.append({
            "inputs": inputs,
            "expected": outputs if outputs else ["<define based on business logic>"]
        })
    else:
        io_matrix.append({
            "inputs": ["<no parameters>"],
            "expected": outputs if outputs else ["<define return value>"]
        })
    
    # Identificar riscos
    risks = []
    if branches == 0:
        risks.append("no conditional branches - may need boundary testing")
    elif branches > complexity:
        risks.append("high branch count relative to complexity")
    
    if not outputs:
        risks.append("return type not detected - verify expected outputs")
        
    if side_effects:
        risks.append(f"side effects detected: {', '.join(side_effects)}")
    
    if not risks:
        risks.append("low risk - straightforward function")
    
    # Overview conciso
    func_names = [f.get('name', 'unknown') for f in functions] if functions else ['<unnamed>']
    overview = (
        f"Functions: {func_names}. "
        f"Inputs: {inputs if inputs else ['none']}. "
        f"Outputs: {outputs if outputs else ['undefined']}. "
        f"Complexity={complexity}, Branches={branches}."
    )
    
    flow_summary = {
        "overview": overview,
        "key_paths": key_paths,
        "edge_cases": edge_cases,
        "io_matrix": io_matrix,
        "risks": risks
    }
    
    print(f"[INFO] Flow summary generated. Paths: {len(key_paths)}, Edge cases: {len(edge_cases)}", file=sys.stderr)
    return flow_summary

@mcp.tool()
def build_prompt(flow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constrói um prompt otimizado para LLM gerar testes unitários
    
    Args:
        flow: Resumo do fluxo de summarize_flow
        
    Returns:
        Prompt estruturado com guardrails e estimativa de tokens
    """
    print("[INFO] Building test generation prompt...", file=sys.stderr)
    
    # Guardrails essenciais
    guardrails = [
        "Não invente dependências; se faltar contexto, peça explicitamente.",
        "Cubra todos os branches mapeados em key_paths.",
        "Inclua casos limite descritos em edge_cases.", 
        "Use nomes de métodos/classe existentes; não renomeie.",
        "Gere testes executáveis e compiláveis.",
        "Adicione assertions adequadas para cada cenário.",
        "Comente apenas casos complexos ou não-óbvios."
    ]
    
    # Template do prompt
    prompt = f"""Você é um agente especializado em geração de testes unitários.
Analise o código e gere uma suite completa de testes seguindo as especificações abaixo.

RESUMO DA ANÁLISE:
{flow.get('overview', 'Análise não disponível')}

CAMINHOS DE EXECUÇÃO:
{chr(10).join(f"- {path}" for path in flow.get('key_paths', []))}

CASOS LIMITE CRÍTICOS:
{chr(10).join(f"- {case}" for case in flow.get('edge_cases', []))}

MATRIZ DE ENTRADA/SAÍDA:
{chr(10).join(f"- Inputs: {io['inputs']} → Expected: {io['expected']}" for io in flow.get('io_matrix', []))}

RISCOS IDENTIFICADOS:
{chr(10).join(f"- {risk}" for risk in flow.get('risks', []))}

REGRAS DE GERAÇÃO:
{chr(10).join(f"- {rule}" for rule in guardrails)}

FORMATO DE SAÍDA ESPERADO:
- Java: Classe JUnit 5 completa com @Test, @BeforeEach, @AfterEach quando necessário
- Python: Testes pytest com fixtures e parametrize quando apropriado  
- TypeScript/JavaScript: Testes Jest com describe/it e mocks quando necessário

INSTRUÇÕES FINAIS:
- Gere APENAS o código dos testes, sem explicações adicionais
- Inclua imports/dependencies necessários
- Organize os testes por cenário (happy path, edge cases, error cases)
- Use nomes descritivos para os métodos de teste
- Adicione setup/teardown apenas quando necessário"""

    # Estimativa simples de tokens (aproximação: 1 token ≈ 0.75 palavras)
    tokens_est = int(len(prompt.split()) * 1.33)
    
    result = {
        "prompt": prompt.strip(),
        "tokens_est": tokens_est,
        "guardrails": guardrails
    }
    
    # Cache para resource
    global last_prompts
    last_prompts.append({
        "timestamp": time.time(),
        "tokens_est": tokens_est,
        "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt
    })
    last_prompts = last_prompts[-10:]
    
    print(f"[INFO] Prompt built. Estimated tokens: {tokens_est}", file=sys.stderr)
    return result

@mcp.tool()
def run_full_pipeline(language: str, code: str) -> Dict[str, Any]:
    """
    Executa o pipeline completo: análise → resumo → prompt
    
    Args:
        language: Linguagem do código (java, python, typescript, js)
        code: Código fonte da função
        
    Returns:
        Resultado consolidado com análise, fluxo, prompt e metadados
    """
    t0 = time.time()
    errors = []
    
    print(f"[INFO] Starting full pipeline for {language}...", file=sys.stderr)
    
    # Etapa 1: Análise
    print("[INFO] Step 1/3: Static analysis...", file=sys.stderr)
    analysis = analyze_function(language, code)
    if "error" in analysis.get("raw", {}):
        errors.append(f"Analysis: {analysis['raw']['error']}")
    
    # Etapa 2: Resumo do fluxo
    print("[INFO] Step 2/3: Flow summarization...", file=sys.stderr)
    try:
        flow = summarize_flow(analysis)
    except Exception as e:
        flow = {"error": f"Flow summary failed: {str(e)}"}
        errors.append(f"Flow: {str(e)}")
    
    # Etapa 3: Construção do prompt
    print("[INFO] Step 3/3: Prompt generation...", file=sys.stderr)
    try:
        prompt = build_prompt(flow)
    except Exception as e:
        prompt = {"error": f"Prompt build failed: {str(e)}"}
        errors.append(f"Prompt: {str(e)}")
    
    t1 = time.time()
    
    result = {
        "analysis": analysis,
        "flow": flow,
        "prompt": prompt,
        "meta": {
            "started_at": t0,
            "finished_at": t1,
            "duration_ms": int((t1 - t0) * 1000),
            "errors": errors,
            "language": language,
            "steps_completed": 3 if not errors else 3 - len([e for e in errors if "failed" in e])
        }
    }
    
    print(f"[INFO] Pipeline completed in {result['meta']['duration_ms']}ms. Errors: {len(errors)}", file=sys.stderr)
    return result

# Resources MCP para cache
@mcp.resource("mcp://last-analyses")
def get_last_analyses():
    """Retorna as últimas análises executadas"""
    return {
        "description": "Cache das últimas análises estáticas executadas",
        "count": len(last_analyses),
        "analyses": last_analyses
    }

@mcp.resource("mcp://last-prompts") 
def get_last_prompts():
    """Retorna os últimos prompts gerados"""
    return {
        "description": "Cache dos últimos prompts gerados para LLM",
        "count": len(last_prompts),
        "prompts": last_prompts
    }

if __name__ == "__main__":
    print("[INFO] Starting MCP Orchestrator server...", file=sys.stderr)
    print("[INFO] Available tools: analyze_function, summarize_flow, build_prompt, run_full_pipeline", file=sys.stderr)
    print("[INFO] Supported languages: Java (via Spring Boot), Python, TypeScript/JavaScript", file=sys.stderr)
    mcp.run()