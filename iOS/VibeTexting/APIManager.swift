//
//  APIManager.swift
//  VibeTexting
//
//  Handles all API communication with the FastAPI backend.
//  Singleton pattern for shared access throughout the app.
//

import Foundation

/// Manages API communication with the backend server
@MainActor
class APIManager: ObservableObject {
    static let shared = APIManager()

    /// Backend server URL - update for production
    private let baseURL: String = ProcessInfo.processInfo.environment["BACKEND_URL"] ?? "http://127.0.0.1:8000"
    
    private let session: URLSession
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
    }
    
    /// Health check to verify backend connectivity
    func checkHealth() async throws -> Bool {
        guard let url = URL(string: "\(baseURL)/health") else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await session.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        let health = try JSONDecoder().decode(HealthResponse.self, from: data)
        return health.status == "healthy"
    }
    
    /// Generate AI reply based on message and tone
    func generateReply(originalMessage: String, userReply: String?, tone: Tone) async throws -> MessageResponse {
        guard let url = URL(string: "\(baseURL)/generate-reply") else {
            throw APIError.invalidURL
        }
        
        let request = MessageRequest(
            originalMessage: originalMessage,
            userReply: userReply,
            tone: tone.rawValue.lowercased(),
            context: nil
        )
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try JSONEncoder().encode(request)
        
        let (data, response) = try await session.data(for: urlRequest)
        
        // Debug: Print raw response
        if let jsonString = String(data: data, encoding: .utf8) {
            print("DEBUG: Received response: \(jsonString)")
        }
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            print("DEBUG: Server returned error code: \(httpResponse.statusCode)")
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        do {
            let decoded = try JSONDecoder().decode(MessageResponse.self, from: data)
            print("DEBUG: Successfully decoded response: \(decoded.generatedReply)")
            return decoded
        } catch {
            print("DEBUG: Decoding error: \(error)")
            throw error
        }
    }
    
    /// Generate alternative replies
    func generateAlternatives(originalMessage: String, userReply: String?, tone: Tone) async throws -> [String] {
        guard let url = URL(string: "\(baseURL)/generate-alternatives") else {
            throw APIError.invalidURL
        }
        
        let request = MessageRequest(
            originalMessage: originalMessage,
            userReply: userReply,
            tone: tone.rawValue.lowercased(),
            context: nil
        )
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try JSONEncoder().encode(request)
        
        let (data, response) = try await session.data(for: urlRequest)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.serverError((response as? HTTPURLResponse)?.statusCode ?? 500)
        }
        
        return try JSONDecoder().decode([String].self, from: data)
    }
}

// MARK: - Supporting Types

struct HealthResponse: Codable {
    let status: String
    let version: String
}

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case serverError(Int)
    case networkError(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid server URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .serverError(let code):
            return "Server error: \(code)"
        case .networkError(let error):
            return error.localizedDescription
        }
    }
}
