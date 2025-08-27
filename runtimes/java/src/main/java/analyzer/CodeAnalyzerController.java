package analyzer;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.stmt.*;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

@RestController
@RequestMapping("/")
public class CodeAnalyzerController {

    @PostMapping("/analyze")
    public ResponseEntity<Map<String, Object>> analyzeCode(@RequestBody Map<String, String> request) {
        try {
            String code = request.get("code");
            if (code == null || code.trim().isEmpty()) {
                return ResponseEntity.badRequest().body(createErrorResponse("No code provided"));
            }

            JavaCodeAnalyzer analyzer = new JavaCodeAnalyzer();
            Map<String, Object> result = analyzer.analyze(code);
            
            return ResponseEntity.ok(result);
            
        } catch (Exception e) {
            return ResponseEntity.status(500).body(createErrorResponse("Analysis failed: " + e.getMessage()));
        }
    }

    private Map<String, Object> createErrorResponse(String message) {
        Map<String, Object> error = new HashMap<>();
        error.put("error", message);
        return error;
    }

    static class JavaCodeAnalyzer {
        private List<Map<String, Object>> functions = new ArrayList<>();
        private int totalBranches = 0;
        private int complexity = 0;
        private Set<String> sideEffects = new HashSet<>();

        public Map<String, Object> analyze(String code) {
            try {
                JavaParser parser = new JavaParser();
                ParseResult<CompilationUnit> parseResult = parser.parse(code);
                
                if (!parseResult.isSuccessful()) {
                    Map<String, Object> error = new HashMap<>();
                    error.put("error", "Parse error: " + parseResult.getProblems());
                    return error;
                }

                CompilationUnit cu = parseResult.getResult().get();
                
                // Visitar e analisar métodos
                MethodAnalyzerVisitor visitor = new MethodAnalyzerVisitor();
                cu.accept(visitor, null);

                // Montar resultado
                Map<String, Object> result = new HashMap<>();
                result.put("functions", functions);
                result.put("inputs", collectAllInputs());
                result.put("outputs", collectAllOutputs());
                result.put("complexity", complexity);
                result.put("branches", totalBranches);
                result.put("side_effects", new ArrayList<>(sideEffects));

                return result;

            } catch (Exception e) {
                Map<String, Object> error = new HashMap<>();
                error.put("error", "Analysis error: " + e.getMessage());
                return error;
            }
        }

        private List<String> collectAllInputs() {
            List<String> allInputs = new ArrayList<>();
            for (Map<String, Object> func : functions) {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> inputs = (List<Map<String, Object>>) func.get("inputs");
                for (Map<String, Object> input : inputs) {
                    String inputStr = input.get("name") + ": " + input.get("type");
                    if (!allInputs.contains(inputStr)) {
                        allInputs.add(inputStr);
                    }
                }
            }
            return allInputs;
        }

        private List<String> collectAllOutputs() {
            List<String> allOutputs = new ArrayList<>();
            for (Map<String, Object> func : functions) {
                @SuppressWarnings("unchecked")
                List<String> outputs = (List<String>) func.get("outputs");
                for (String output : outputs) {
                    if (!allOutputs.contains(output)) {
                        allOutputs.add(output);
                    }
                }
            }
            return allOutputs;
        }

        class MethodAnalyzerVisitor extends VoidVisitorAdapter<Void> {
            
            @Override
            public void visit(MethodDeclaration method, Void arg) {
                Map<String, Object> methodInfo = analyzeMethod(method);
                functions.add(methodInfo);
                
                // Somar métricas globais
                totalBranches += (Integer) methodInfo.get("branches");
                complexity += (Integer) methodInfo.get("local_complexity");
                
                super.visit(method, arg);
            }

            private Map<String, Object> analyzeMethod(MethodDeclaration method) {
                Map<String, Object> methodInfo = new HashMap<>();
                
                methodInfo.put("name", method.getNameAsString());
                methodInfo.put("inputs", extractInputs(method));
                methodInfo.put("outputs", extractOutputs(method));
                methodInfo.put("line_start", method.getRange().map(r -> r.begin.line).orElse(0));
                methodInfo.put("line_end", method.getRange().map(r -> r.end.line).orElse(0));
                
                // Analisar complexidade e branches
                ComplexityAnalyzer complexityAnalyzer = new ComplexityAnalyzer();
                method.accept(complexityAnalyzer, null);
                
                methodInfo.put("branches", complexityAnalyzer.getBranches());
                methodInfo.put("local_complexity", complexityAnalyzer.getComplexity());
                
                // Detectar side effects
                SideEffectDetector sideEffectDetector = new SideEffectDetector();
                method.accept(sideEffectDetector, null);
                sideEffects.addAll(sideEffectDetector.getSideEffects());
                
                return methodInfo;
            }

            private List<Map<String, Object>> extractInputs(MethodDeclaration method) {
                List<Map<String, Object>> inputs = new ArrayList<>();
                
                for (Parameter param : method.getParameters()) {
                    Map<String, Object> paramInfo = new HashMap<>();
                    paramInfo.put("name", param.getNameAsString());
                    paramInfo.put("type", param.getTypeAsString());
                    paramInfo.put("is_varargs", param.isVarArgs());
                    inputs.add(paramInfo);
                }
                
                return inputs;
            }

            private List<String> extractOutputs(MethodDeclaration method) {
                List<String> outputs = new ArrayList<>();
                
                Type returnType = method.getType();
                outputs.add(returnType.asString());
                
                return outputs;
            }
        }

        class ComplexityAnalyzer extends VoidVisitorAdapter<Void> {
            private int branches = 0;
            private int complexity = 1; // Base complexity
            
            public int getBranches() { return branches; }
            public int getComplexity() { return complexity; }

            @Override
            public void visit(IfStmt n, Void arg) {
                branches++;
                complexity++;
                super.visit(n, arg);
            }

            @Override
            public void visit(SwitchStmt n, Void arg) {
                int caseCount = n.getEntries().size();
                branches += Math.max(1, caseCount);
                complexity += Math.max(1, caseCount);
                super.visit(n, arg);
            }

            @Override
            public void visit(ForStmt n, Void arg) {
                branches++;
                complexity++;
                super.visit(n, arg);
            }

            @Override
            public void visit(ForEachStmt n, Void arg) {
                branches++;
                complexity++;
                super.visit(n, arg);
            }

            @Override
            public void visit(WhileStmt n, Void arg) {
                branches++;
                complexity++;
                super.visit(n, arg);
            }

            @Override
            public void visit(DoStmt n, Void arg) {
                branches++;
                complexity++;
                super.visit(n, arg);
            }

            @Override
            public void visit(TryStmt n, Void arg) {
                branches++; // Try block
                branches += n.getCatchClauses().size(); // Each catch
                if (n.getFinallyBlock().isPresent()) {
                    branches++; // Finally block
                }
                complexity += (1 + n.getCatchClauses().size());
                super.visit(n, arg);
            }

            @Override
            public void visit(ConditionalExpr n, Void arg) {
                branches++;
                complexity++;
                super.visit(n, arg);
            }
        }

        class SideEffectDetector extends VoidVisitorAdapter<Void> {
            private Set<String> detectedSideEffects = new HashSet<>();
            
            public Set<String> getSideEffects() { return detectedSideEffects; }

            @Override
            public void visit(MethodCallExpr n, Void arg) {
                String methodName = n.getNameAsString();
                
                // IO operations
                if (methodName.matches("print|println|printf|write|read|flush|close")) {
                    detectedSideEffects.add("io_operations");
                }
                
                // System operations
                if (methodName.matches("exit|gc|currentTimeMillis|nanoTime")) {
                    detectedSideEffects.add("system_operations");
                }
                
                // Network operations (heurística)
                if (methodName.matches("connect|send|receive|get|post|put|delete")) {
                    detectedSideEffects.add("network_operations");
                }
                
                // Database operations (heurística)
                if (methodName.matches("execute|query|update|insert|delete|commit|rollback")) {
                    detectedSideEffects.add("database_operations");
                }
                
                // File operations
                if (methodName.matches("create|delete|move|copy|exists|mkdir")) {
                    detectedSideEffects.add("file_operations");
                }
                
                // Reflection
                if (methodName.matches("getClass|forName|newInstance|invoke")) {
                    detectedSideEffects.add("reflection");
                }
                
                super.visit(n, arg);
            }

            @Override
            public void visit(AssignExpr n, Void arg) {
                // Detectar modificação de campos estáticos ou atributos de classe
                if (n.getTarget() instanceof FieldAccessExpr) {
                    FieldAccessExpr field = (FieldAccessExpr) n.getTarget();
                    if (field.getScope() instanceof NameExpr) {
                        detectedSideEffects.add("external_state_modification");
                    }
                }
                super.visit(n, arg);
            }

            @Override
            public void visit(ThrowStmt n, Void arg) {
                detectedSideEffects.add("exception_throwing");
                super.visit(n, arg);
            }

            @Override
            public void visit(SynchronizedStmt n, Void arg) {
                detectedSideEffects.add("synchronization");
                super.visit(n, arg);
            }
        }
    }
}