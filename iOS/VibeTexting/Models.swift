//
//  Models.swift
//  VibeTexting
//
//  Data models for the VibeTexting app.
//  These models represent the data structures used throughout the app.
//

import Foundation

/// Represents a message the user received and wants to reply to
struct ReceivedMessage: Identifiable, Codable {
    let id: UUID
    var content: String
    var source: String  // e.g., "Messages", "WhatsApp"
    var timestamp: Date
    
    init(id: UUID = UUID(), content: String, source: String = "Unknown", timestamp: Date = Date()) {
        self.id = id
        self.content = content
        self.source = source
        self.timestamp = timestamp
    }
}

/// Represents tone options for AI-generated responses
enum Tone: String, CaseIterable, Identifiable, Codable {
    case casual = "Casual"
    case professional = "Professional"
    case funny = "Funny"
    case friendly = "Friendly"
    case concise = "Concise"
    
    var id: String { self.rawValue }
    
    /// Icon representation for each tone
    var icon: String {
        switch self {
        case .casual: return "😎"
        case .professional: return "💼"
        case .funny: return "😄"
        case .friendly: return "🤗"
        case .concise: return "⚡"
        }
    }
    
    /// Description for UI tooltips
    var description: String {
        switch self {
        case .casual: return "Relaxed and conversational"
        case .professional: return "Polite and business-appropriate"
        case .funny: return "Humorous and playful"
        case .friendly: return "Warm and supportive"
        case .concise: return "Brief and direct"
        }
    }
}

/// Request model for API calls
struct MessageRequest: Codable {
    let originalMessage: String
    let userReply: String?
    let tone: String
    let context: String?
    
    enum CodingKeys: String, CodingKey {
        case originalMessage = "original_message"
        case userReply = "user_reply"
        case tone
        case context
    }
}

/// Response model from API
struct MessageResponse: Codable {
    let generatedReply: String
    let tone: String
    let alternatives: [String]?
    
    enum CodingKeys: String, CodingKey {
        case generatedReply = "generated_reply"
        case tone
        case alternatives
    }
}

/// Represents a generated reply with metadata
struct GeneratedReply: Identifiable, Codable {
    let id: UUID
    var content: String
    var tone: Tone
    var timestamp: Date
    var isFavorite: Bool
    
    init(id: UUID = UUID(), content: String, tone: Tone, timestamp: Date = Date(), isFavorite: Bool = false) {
        self.id = id
        self.content = content
        self.tone = tone
        self.timestamp = timestamp
        self.isFavorite = isFavorite
    }
}

