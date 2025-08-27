package analyzer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

@SpringBootApplication
@RestController
public class JavaAnalyzerApplication {

    public static void main(String[] args) {
        System.out.println("Starting MCP Java Code Analyzer Service...");
        System.out.println("Service will be available at: http://localhost:8080");
        System.out.println("Endpoint: POST /analyze");
        SpringApplication.run(JavaAnalyzerApplication.class, args);
    }

    @GetMapping("/")
    public Map<String, Object> home() {
        Map<String, Object> response = new HashMap<>();
        response.put("service", "MCP Java Code Analyzer");
        response.put("version", "1.0.0");
        response.put("status", "running");
        response.put("endpoints", Map.of(
            "analyze", "POST /analyze - Analyze Java code"
        ));
        response.put("usage", "Send POST request with JSON body: {\"code\": \"your java code here\"}");
        return response;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        Map<String, String> response = new HashMap<>();
        response.put("status", "UP");
        response.put("service", "java-analyzer");
        return response;
    }
}