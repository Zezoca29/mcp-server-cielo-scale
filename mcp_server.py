from fastmcp import FastMCP
import requests
import subprocess
import json
import time
import sys
import os
from typing import Dict, Any, List
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mcp = FastMCP("mcp-orchestrator")

# Cache para resources MCP
last_analyses = []
last_prompts = []

def _check_runtime_availability() -> Dict[str, bool]:
    """Verifica quais runtimes estão disponíveis"""
    availability = {
        "java": False,
        "python": False, 
        "typescript": False
    }
    
    # Verificar Java Spring Boot service
    try:
        response = requests.get("http://localhost:8080/health", timeout=2)
        if response.status_code == 200:
            availability["java"] = True
            logger.info("Java analyzer service is available")
    except requests.RequestException:
        logger.warning("Java analyzer service is not available")
    
    # Verificar Python analyzer
    python_analyzer = os.path.join("runtimes", "python", "analyzer.py")
    if os.path.exists(python_analyzer):
        availability["python"] = True
        logger.info("Python analyzer is available")
    else:
        logger.warning(f"Python analyzer not found at {python_analyzer}")
    
    # Verificar TypeScript analyzer
    ts_analyzer = os.path.join("runtimes", "ts", "analyzer.js")
    if os.path.exists(ts_analyzer):
        # Verificar se node e ts-morph estão disponíveis
        try:
            result = subprocess.run(
                ["node", "-e", "require('ts-morph'); console.log('ok')"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                availability["typescript"] = True
                logger.info("TypeScript analyzer is available")
            else:
                logger.warning("TypeScript analyzer found but ts-morph dependency missing")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Node.js not available for TypeScript analyzer")
    else:
        logger.warning(f"TypeScript analyzer not found at {ts_analyzer}")
    
    return availability

def _dispatch_analyze(language: str, code: str) -> Dict[str, Any]:
    """Despacha análise para o runtime apropriado baseado na linguagem"""
    lang = language.lower()
    
    # Normalizar variações de linguagem
    if lang in ["ts", "typescript"]:
        lang = "typescript"
    elif lang in ["js", "javascript"]:
        lang = "typescript"  # Usar mesmo analyzer
    
    try:
        if lang == "java":
            logger.info("Dispatching Java analysis to Spring Boot service...")
            try:
                r = requests.post(
                    "http://localhost:8080/analyze", 
                    json={"code": code}, 
                    timeout=15,
                    headers={"Content-Type": "application/json"}
                )
                r.raise_for_status()
                return r.json()
            except requests.ConnectionError:
                return {"error": "Java analyzer service not available. Please start the Spring Boot service on port 8080."}
            except requests.Timeout:
                return {"error": "Java analyzer service timeout. The code may be too complex."}
            
        elif lang == "python":
            logger.info("Dispatching Python analysis to local analyzer...")
            analyzer_path = os.path.join("runtimes", "python", "analyzer.py")
            if not os.path.exists(analyzer_path):
                return {"error": f"Python analyzer not found. Please ensure {analyzer_path} exists."}
                
            try:
                p = subprocess.run(
                    [sys.executable, analyzer_path],
                    input=code.encode("utf-8"),
                    capture_output=True, 
                    timeout=15
                )
                
                if p.returncode != 0:
                    error_msg = p.stderr.decode() if p.stderr else "Unknown error"
                    return {"error": f"Python analyzer failed: {error_msg}"}
                    
                result = p.stdout.decode().strip()
                if not result:
                    return {"error": "Python analyzer returned empty result"}
                    
                return json.loads(result)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON from Python analyzer: {str(e)}"}
            
        elif lang == "typescript":
            logger.info("Dispatching TypeScript/JS analysis to Node analyzer...")
            analyzer_path = os.path.join("runtimes", "ts", "analyzer.js")
            if not os.path.exists(analyzer_path):
                return {"error": f"TypeScript analyzer not found. Please ensure {analyzer_path} exists."}
                
            try:
                p = subprocess.run(
                    ["node", analyzer_path],
                    input=code.encode("utf-8"),
                    capture_output=True, 
                    timeout=15
                )
                
                if p.returncode != 0:
                    error_msg = p.stderr.decode() if p.stderr else "Unknown error"
                    return {"error": f"TypeScript analyzer failed: {error_msg}"}
                    
                result = p.stdout.decode().strip()
                if not result:
                    return {"error": "TypeScript analyzer returned empty result"}
                    
                return json.loads(result)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON from TypeScript analyzer: {str(e)}"}
            
        else:
            supported = ["java", "python", "typescript", "javascript", "ts", "js"]
            return {"error": f"Unsupported language: '{language}'. Supported languages: {', '.join(supported)}"}
            
    except subprocess.TimeoutExpired:
        return {"error": f"Analysis timeout for {language}. The code may be too complex or contain infinite loops."}
    except Exception as e:
        return {"error": f"Unexpected error in {language} analysis: {str(e)}"}

def _validate_code_input(code: str) -> Dict[str, Any]:
    """Valida entrada de código"""
    if not code or not isinstance(code, str):
        return {"error": "Code must be a non-empty string"}
    
    if len(code.strip()) == 0:
        return {"error": "Code cannot be empty or only whitespace"}
    
    if len(code) > 50000:  # Limite de 50KB
        return {"error": "Code is too large (max 50KB allowed)"}
    
    return {"valid": True}

@mcp.tool()
def check_runtime_status() -> Dict[str, Any]:
    """
    Verifica o status dos runtimes de análise disponíveis
    
    Returns:
        Status de cada runtime (Java, Python, TypeScript)
    """
    logger.info("Checking runtime availability...")
    
    availability = _check_runtime_availability()
    
    status = {
        "available_runtimes": [lang for lang, available in availability.items() if available],
        "unavailable_runtimes": [lang for lang, available in availability.items() if not available],
        "details": availability,
        "total_available": sum(availability.values()),
        "recommendations": []
    }
    
    # Adicionar recomendações baseadas no status
    if not availability["java"]:
        status["recommendations"].append("Start Java analyzer: cd runtimes/java && ./mvnw spring-boot:run")
    if not availability["python"]:
        status["recommendations"].append("Ensure Python analyzer exists at runtimes/python/analyzer.py")
    if not availability["typescript"]:
        status["recommendations"].append("Install dependencies: cd runtimes/ts && npm install ts-morph")
    
    return status

@mcp.tool()
def analyze_function(language: str, code: str) -> Dict[str, Any]:
    """
    Analisa estaticamente uma função em Java, Python ou TypeScript
    
    Args:
        language: Linguagem do código (java, python, typescript, js, ts)
        code: Código fonte da função
        
    Returns:
        Análise estrutural da função com inputs, outputs, complexidade, branches
    """
    logger.info(f"Starting analysis for {language} code...")
    
    # Validar entrada
    validation = _validate_code_input(code)
    if "error" in validation:
        return validation
    
    result = _dispatch_analyze(language, code)
    
    # Se houve erro na análise, retornar imediatamente
    if "error" in result:
        return result
    
    # Normalização e defaults para garantir contrato consistente
    normalized = {
        "language": language.lower(),
        "functions": result.get("functions", []),
        "inputs": result.get("inputs", []),
        "outputs": result.get("outputs", []),
        "complexity": result.get("complexity", 0),
        "branches": result.get("branches", 0),
        "side_effects": result.get("side_effects", []),
        "analysis_metadata": {
            "timestamp": time.time(),
            "analyzer_version": "1.0.0",
            "success": True
        },
        "raw": result
    }
    
    # Cache para resource
    global last_analyses
    last_analyses.append({
        "timestamp": time.time(),
        "language": language,
        "result": normalized,
        "code_length": len(code),
        "success": True
    })
    # Manter apenas os últimos 10
    last_analyses = last_analyses[-10:]
    
    logger.info(f"Analysis completed. Functions: {len(normalized['functions'])}, Branches: {normalized['branches']}")
    return normalized

@mcp.tool()
def summarize_flow(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resume o fluxo de execução baseado na análise estática
    
    Args:
        analysis: Resultado da análise de analyze_function
        
    Returns:
        Resumo estruturado com caminhos, casos limite e matriz IO
    """
    logger.info("Summarizing execution flow...")
    
    # Validar entrada
    if not isinstance(analysis, dict):
        return {"error": "Analysis must be a dictionary object"}
    
    if "error" in analysis:
        return {"error": f"Cannot summarize failed analysis: {analysis['error']}"}
    
    # Extrair métricas com defaults seguros
    complexity = analysis.get("complexity", 0)
    branches = analysis.get("branches", 0)
    functions = analysis.get("functions", [])
    inputs = analysis.get("inputs", [])
    outputs = analysis.get("outputs", [])
    side_effects = analysis.get("side_effects", [])
    language = analysis.get("language", "unknown")
    
    # Gerar caminhos baseados em branches
    num_paths = max(1, branches) if branches > 0 else 1
    key_paths = []
    
    if branches == 0:
        key_paths = ["linear_path"]
    elif branches <= 3:
        key_paths = [f"conditional_path_{i+1}" for i in range(num_paths)]
    else:
        key_paths = [
            "happy_path",
            "edge_case_paths", 
            "error_handling_paths",
            f"complex_branching_{branches}_branches"
        ]
    
    # Casos limite específicos por linguagem
    edge_cases = []
    
    # Casos comuns
    base_cases = ["null/None/undefined inputs", "empty collections", "boundary values (0, -1, max)"]
    edge_cases.extend(base_cases)
    
    # Casos específicos por linguagem
    if language == "java":
        edge_cases.extend(["NullPointerException scenarios", "IndexOutOfBoundsException", "ClassCastException"])
    elif language == "python":
        edge_cases.extend(["TypeError scenarios", "ValueError", "KeyError/IndexError"])
    elif language in ["typescript", "javascript"]:
        edge_cases.extend(["undefined/null handling", "type coercion edge cases", "async/await errors"])
    
    # Casos baseados em side effects
    if "io_operations" in side_effects:
        edge_cases.append("IO failures and timeouts")
    if "network_operations" in side_effects:
        edge_cases.append("network connectivity issues")
    if "database_operations" in side_effects:
        edge_cases.append("database connection/transaction failures")
    if "async_operations" in side_effects:
        edge_cases.append("async operation failures and race conditions")
    
    if complexity > 5:
        edge_cases.append("high complexity execution paths")
    
    # Matriz IO para teste com exemplos mais específicos
    io_matrix = []
    
    if inputs:
        # Gerar casos de teste baseados nos inputs
        for i, input_def in enumerate(inputs[:3]):  # Limitar a 3 exemplos
            test_case = {
                "test_case": f"scenario_{i+1}",
                "inputs": input_def,
                "expected_outputs": outputs if outputs else ["<define based on business logic>"],
                "description": f"Test case for input: {input_def}"
            }
            io_matrix.append(test_case)
    else:
        io_matrix.append({
            "test_case": "no_parameters",
            "inputs": ["<no parameters>"],
            "expected_outputs": outputs if outputs else ["<define return value>"],
            "description": "Function with no parameters"
        })
    
    # Identificar riscos e recomendações
    risks = []
    recommendations = []
    
    if branches == 0:
        risks.append("no conditional branches detected")
        recommendations.append("verify if boundary testing is needed")
    elif branches > complexity * 2:
        risks.append("high branch count relative to complexity")
        recommendations.append("consider breaking down into smaller functions")
    
    if not outputs or outputs == ["void", "None", "undefined"]:
        risks.append("no meaningful return value detected")
        recommendations.append("verify expected outputs and side effects")
        
    if side_effects:
        risks.append(f"side effects detected: {', '.join(side_effects)}")
        recommendations.append("ensure proper mocking/stubbing for side effects in tests")
    
    if complexity > 10:
        risks.append("high cyclomatic complexity")
        recommendations.append("consider refactoring to reduce complexity")
    
    if len(functions) > 1:
        recommendations.append("test each function separately and integration scenarios")
    
    if not risks:
        risks.append("low risk - straightforward function structure")
    
    # Overview mais detalhado
    func_names = [f.get('name', 'unknown') for f in functions] if functions else ['<unnamed>']
    overview = (
        f"Language: {language.upper()}. "
        f"Functions analyzed: {func_names}. "
        f"Input parameters: {len(inputs)} ({', '.join(inputs[:2])}{'...' if len(inputs) > 2 else ''}). "
        f"Return types: {outputs}. "
        f"Cyclomatic complexity: {complexity}, Decision branches: {branches}. "
        f"Side effects: {len(side_effects)} detected."
    )
    
    flow_summary = {
        "overview": overview,
        "key_paths": key_paths,
        "edge_cases": edge_cases,
        "io_matrix": io_matrix,
        "risks": risks,
        "recommendations": recommendations,
        "metrics": {
            "complexity": complexity,
            "branches": branches,
            "functions_count": len(functions),
            "inputs_count": len(inputs),
            "outputs_count": len(outputs),
            "side_effects_count": len(side_effects)
        }
    }
    
    logger.info(f"Flow summary generated. Paths: {len(key_paths)}, Edge cases: {len(edge_cases)}")
    return flow_summary

@mcp.tool()
def build_prompt(flow: Dict[str, Any], test_framework: str = "auto") -> Dict[str, Any]:
    """
    Constrói um prompt otimizado para LLM gerar testes unitários
    
    Args:
        flow: Resumo do fluxo de summarize_flow
        test_framework: Framework de teste preferido ("auto", "junit", "pytest", "jest")
        
    Returns:
        Prompt estruturado com guardrails e estimativa de tokens
    """
    logger.info("Building test generation prompt...")
    
    # Validar entrada
    if not isinstance(flow, dict):
        return {"error": "Flow must be a dictionary object"}
    
    if "error" in flow:
        return {"error": f"Cannot build prompt from failed flow analysis: {flow['error']}"}
    
    # Determinar framework baseado na linguagem se "auto"
    language = flow.get("metrics", {}).get("language", "unknown")
    if test_framework == "auto":
        framework_map = {
            "java": "junit5",
            "python": "pytest", 
            "typescript": "jest",
            "javascript": "jest"
        }
        test_framework = framework_map.get(language, "generic")
    
    # Guardrails específicos por framework
    framework_guardrails = {
        "junit5": [
            "Use JUnit 5 annotations (@Test, @BeforeEach, @AfterEach, @DisplayName)",
            "Use assertThat() from AssertJ or assertEquals() from JUnit",
            "Create @Mock objects for dependencies using Mockito",
            "Use @ParameterizedTest for multiple test cases"
        ],
        "pytest": [
            "Use pytest fixtures for setup and teardown", 
            "Use pytest.parametrize for multiple test cases",
            "Use assert statements for verification",
            "Use unittest.mock for mocking dependencies"
        ],
        "jest": [
            "Use describe() and it() blocks for organization",
            "Use beforeEach() and afterEach() for setup/teardown",
            "Use jest.mock() and jest.spyOn() for mocking",
            "Use expect() assertions with appropriate matchers"
        ],
        "generic": [
            "Use appropriate testing framework conventions",
            "Include proper setup and teardown",
            "Mock external dependencies",
            "Use descriptive test names"
        ]
    }
    
    # Guardrails essenciais
    base_guardrails = [
        "Generate ONLY executable test code without explanations",
        "Cover ALL execution paths identified in key_paths",
        "Include test cases for ALL edge cases listed",
        "Use exact function/class names from original code - DO NOT rename",
        "Add meaningful assertions for each scenario", 
        "Include necessary imports and dependencies",
        "Create one test method per logical scenario"
    ]
    
    guardrails = base_guardrails + framework_guardrails.get(test_framework, [])
    
    # Template do prompt melhorado
    prompt = f"""You are an expert test generation agent specialized in {test_framework} testing framework.

ANALYSIS SUMMARY:
{flow.get('overview', 'Analysis not available')}

EXECUTION PATHS TO COVER:
{chr(10).join(f"✓ {path}" for path in flow.get('key_paths', []))}

CRITICAL EDGE CASES:
{chr(10).join(f"⚠ {case}" for case in flow.get('edge_cases', []))}

INPUT/OUTPUT TEST MATRIX:
{chr(10).join(f"📊 {io.get('description', 'Test case')}: {io.get('inputs', [])} → {io.get('expected_outputs', [])}" for io in flow.get('io_matrix', []))}

IDENTIFIED RISKS & RECOMMENDATIONS:
{chr(10).join(f"🔍 {risk}" for risk in flow.get('risks', []))}
{chr(10).join(f"💡 {rec}" for rec in flow.get('recommendations', []))}

TEST GENERATION RULES:
{chr(10).join(f"• {rule}" for rule in guardrails)}

EXPECTED OUTPUT FORMAT:
"""

    # Adicionar templates específicos por framework
    if test_framework == "junit5":
        prompt += """
```java
import org.junit.jupiter.api.*;
import static org.assertj.core.api.Assertions.*;
// ... other imports

class FunctionNameTest {
    @Test
    @DisplayName("should handle normal case")
    void shouldHandleNormalCase() {
        // Arrange
        // Act  
        // Assert
    }
    
    // ... more test methods
}
```"""
    elif test_framework == "pytest":
        prompt += """
```python
import pytest
from unittest.mock import Mock, patch
# ... other imports

class TestFunctionName:
    def test_should_handle_normal_case(self):
        # Arrange
        # Act
        # Assert
        
    # ... more test methods
```"""
    elif test_framework == "jest":
        prompt += """
```typescript
import { functionName } from './module';
// ... other imports

describe('functionName', () => {
    it('should handle normal case', () => {
        // Arrange
        // Act
        // Assert
    });
    
    // ... more test cases
});
```"""
    
    prompt += f"""

FINAL INSTRUCTIONS:
- Focus on the {len(flow.get('key_paths', []))} execution paths and {len(flow.get('edge_cases', []))} edge cases
- Ensure {flow.get('metrics', {}).get('branches', 0)} decision branches are tested
- Handle {flow.get('metrics', {}).get('side_effects_count', 0)} side effects appropriately
- Generate complete, compilable, and executable test code"""

    # Estimativa de tokens mais precisa
    words = len(prompt.split())
    tokens_est = int(words * 1.3)  # Ajuste para incluir código gerado
    
    result = {
        "prompt": prompt.strip(),
        "tokens_est": tokens_est,
        "test_framework": test_framework,
        "guardrails": guardrails,
        "metadata": {
            "paths_to_cover": len(flow.get('key_paths', [])),
            "edge_cases_to_test": len(flow.get('edge_cases', [])),
            "io_scenarios": len(flow.get('io_matrix', [])),
            "complexity_level": flow.get('metrics', {}).get('complexity', 0)
        }
    }
    
    # Cache para resource
    global last_prompts
    last_prompts.append({
        "timestamp": time.time(),
        "test_framework": test_framework,
        "tokens_est": tokens_est,
        "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
        "metadata": result["metadata"]
    })
    last_prompts = last_prompts[-10:]
    
    logger.info(f"Prompt built for {test_framework}. Estimated tokens: {tokens_est}")
    return result

@mcp.tool()
def run_full_pipeline(language: str, code: str, test_framework: str = "auto") -> Dict[str, Any]:
    """
    Executa o pipeline completo: análise → resumo → prompt
    
    Args:
        language: Linguagem do código (java, python, typescript, js, ts)
        code: Código fonte da função
        test_framework: Framework de teste preferido (auto, junit5, pytest, jest)
        
    Returns:
        Resultado consolidado com análise, fluxo, prompt e metadados
    """
    t0 = time.time()
    errors = []
    warnings = []
    
    logger.info(f"Starting full pipeline for {language}...")
    
    # Verificar disponibilidade do runtime
    availability = _check_runtime_availability()
    target_lang = language.lower()
    if target_lang in ["ts", "typescript", "js", "javascript"]:
        target_lang = "typescript"
    
    if not availability.get(target_lang, False):
        warnings.append(f"Runtime for {language} may not be available")
    
    # Etapa 1: Análise
    logger.info("Step 1/3: Static analysis...")
    analysis = analyze_function(language, code)
    if "error" in analysis:
        errors.append(f"Analysis failed: {analysis['error']}")
        return {
            "analysis": analysis,
            "errors": errors,
            "warnings": warnings,
            "meta": {
                "started_at": t0,
                "finished_at": time.time(),
                "duration_ms": int((time.time() - t0) * 1000),
                "steps_completed": 0,
                "success": False
            }
        }
    
    # Etapa 2: Resumo do fluxo
    logger.info("Step 2/3: Flow summarization...")
    try:
        flow = summarize_flow(analysis)
        if "error" in flow:
            errors.append(f"Flow summary failed: {flow['error']}")
    except Exception as e:
        flow = {"error": f"Flow summary failed: {str(e)}"}
        errors.append(f"Flow summary exception: {str(e)}")
    
    # Etapa 3: Construção do prompt
    logger.info("Step 3/3: Prompt generation...")
    try:
        if "error" not in flow:
            prompt = build_prompt(flow, test_framework)
            if "error" in prompt:
                errors.append(f"Prompt build failed: {prompt['error']}")
        else:
            prompt = {"error": "Skipped due to flow summary failure"}
            errors.append("Prompt generation skipped")
    except Exception as e:
        prompt = {"error": f"Prompt build failed: {str(e)}"}
        errors.append(f"Prompt generation exception: {str(e)}")
    
    t1 = time.time()
    
    # Calcular steps completados
    steps_completed = 0
    if "error" not in analysis:
        steps_completed += 1
    if "error" not in flow:
        steps_completed += 1
    if "error" not in prompt:
        steps_completed += 1
    
    result = {
        "analysis": analysis,
        "flow": flow,
        "prompt": prompt,
        "errors": errors,
        "warnings": warnings,
        "runtime_status": availability,
        "meta": {
            "started_at": t0,
            "finished_at": t1,
            "duration_ms": int((t1 - t0) * 1000),
            "language": language,
            "test_framework": test_framework,
            "steps_completed": steps_completed,
            "total_steps": 3,
            "success": steps_completed == 3 and len(errors) == 0
        }
    }
    
    logger.info(f"Pipeline completed in {result['meta']['duration_ms']}ms. Success: {result['meta']['success']}, Errors: {len(errors)}")
    return result

# Resources MCP para cache e monitoramento
@mcp.resource("mcp://last-analyses")
def get_last_analyses():
    """Retorna as últimas análises executadas"""
    return {
        "description": "Cache das últimas análises estáticas executadas",
        "count": len(last_analyses),
        "analyses": last_analyses,
        "success_rate": sum(1 for a in last_analyses if a.get("success", False)) / max(len(last_analyses), 1)
    }

@mcp.resource("mcp://last-prompts") 
def get_last_prompts():
    """Retorna os últimos prompts gerados"""
    return {
        "description": "Cache dos últimos prompts gerados para LLM",
        "count": len(last_prompts),
        "prompts": last_prompts,
        "avg_tokens": sum(p.get("tokens_est", 0) for p in last_prompts) / max(len(last_prompts), 1)
    }

@mcp.resource("mcp://system-status")
def get_system_status():
    """Status geral do sistema"""
    availability = _check_runtime_availability()
    return {
        "description": "Status geral do sistema MCP Orchestrator",
        "runtime_availability": availability,
        "total_available_runtimes": sum(availability.values()),
        "cache_stats": {
            "analyses_cached": len(last_analyses),
            "prompts_cached": len(last_prompts)
        },
        "uptime": time.time(),
        "healthy": sum(availability.values()) > 0
    }

if __name__ == "__main__":
    print("[INFO] Starting MCP Orchestrator server...", file=sys.stderr)
    print("[INFO] Available tools: analyze_function, summarize_flow, build_prompt, run_full_pipeline, check_runtime_status", file=sys.stderr)
    print("[INFO] Available resources: mcp://last-analyses, mcp://last-prompts, mcp://system-status", file=sys.stderr)
    
    # Verificar status dos runtimes na inicialização
    availability = _check_runtime_availability()
    available_langs = [lang for lang, avail in availability.items() if avail]
    print(f"[INFO] Available language runtimes: {available_langs}", file=sys.stderr)
    
    if not available_langs:
        print("[WARNING] No language runtimes are available! Please check your setup.", file=sys.stderr)
    
    print("[INFO] Server ready to accept connections.", file=sys.stderr)
    mcp.run()