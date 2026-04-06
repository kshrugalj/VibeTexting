//
//  StorageManager.swift
//  VibeTexting
//
//  Handles local storage for messages, replies, and preferences.
//  Uses UserDefaults for simple data persistence.
//

import Foundation

/// Manages local data persistence
class StorageManager: ObservableObject {
    static let shared = StorageManager()
    
    private let defaults = UserDefaults.standard
    
    // MARK: - Keys
    private enum Keys {
        static let replyHistory = "replyHistory"
        static let favoriteReplies = "favoriteReplies"
        static let defaultTone = "defaultTone"
        static let recentMessages = "recentMessages"
    }
    
    // MARK: - Reply History
    
    /// Save generated reply to history
    func saveReply(_ reply: GeneratedReply) {
        var history = getReplyHistory()
        history.insert(reply, at: 0)
        
        // Keep only last 50 replies
        if history.count > 50 {
            history.removeLast()
        }
        
        saveReplyHistory(history)
    }
    
    /// Get reply history
    func getReplyHistory() -> [GeneratedReply] {
        guard let data = defaults.data(forKey: Keys.replyHistory),
              let replies = try? JSONDecoder().decode([GeneratedReply].self, from: data) else {
            return []
        }
        return replies
    }
    
    /// Clear reply history
    func clearReplyHistory() {
        defaults.removeObject(forKey: Keys.replyHistory)
        objectWillChange.send()
    }
    
    private func saveReplyHistory(_ history: [GeneratedReply]) {
        if let data = try? JSONEncoder().encode(history) {
            defaults.set(data, forKey: Keys.replyHistory)
            objectWillChange.send()
        }
    }
    
    // MARK: - Favorite Replies
    
    /// Toggle favorite status for a reply
    func toggleFavorite(for replyId: UUID) {
        var favorites = getFavoriteReplies()
        
        if let index = favorites.firstIndex(where: { $0.id == replyId }) {
            favorites[index].isFavorite.toggle()
            if !favorites[index].isFavorite {
                favorites.remove(at: index)
            }
        }
        
        saveFavoriteReplies(favorites)
    }
    
    /// Get favorite replies
    func getFavoriteReplies() -> [GeneratedReply] {
        guard let data = defaults.data(forKey: Keys.favoriteReplies),
              let replies = try? JSONDecoder().decode([GeneratedReply].self, from: data) else {
            return []
        }
        return replies.filter { $0.isFavorite }
    }
    
    private func saveFavoriteReplies(_ favorites: [GeneratedReply]) {
        if let data = try? JSONEncoder().encode(favorites) {
            defaults.set(data, forKey: Keys.favoriteReplies)
            objectWillChange.send()
        }
    }
    
    // MARK: - Preferences
    
    /// Get default tone preference
    func getDefaultTone() -> Tone {
        guard let toneRaw = defaults.string(forKey: Keys.defaultTone),
              let tone = Tone(rawValue: toneRaw) else {
            return .casual
        }
        return tone
    }
    
    /// Set default tone preference
    func setDefaultTone(_ tone: Tone) {
        defaults.set(tone.rawValue, forKey: Keys.defaultTone)
        objectWillChange.send()
    }
    
    // MARK: - Recent Messages
    
    /// Save recent message
    func saveRecentMessage(_ message: ReceivedMessage) {
        var messages = getRecentMessages()
        messages.insert(message, at: 0)
        
        // Keep only last 20 messages
        if messages.count > 20 {
            messages.removeLast()
        }
        
        saveRecentMessages(messages)
    }
    
    /// Get recent messages
    func getRecentMessages() -> [ReceivedMessage] {
        guard let data = defaults.data(forKey: Keys.recentMessages),
              let messages = try? JSONDecoder().decode([ReceivedMessage].self, from: data) else {
            return []
        }
        return messages
    }
    
    private func saveRecentMessages(_ messages: [ReceivedMessage]) {
        if let data = try? JSONEncoder().encode(messages) {
            defaults.set(data, forKey: Keys.recentMessages)
            objectWillChange.send()
        }
    }
    
    /// Clear recent messages
    func clearRecentMessages() {
        defaults.removeObject(forKey: Keys.recentMessages)
        objectWillChange.send()
    }
    
    // MARK: - Reset
    
    /// Clear all stored data
    func clearAll() {
        defaults.removeObject(forKey: Keys.replyHistory)
        defaults.removeObject(forKey: Keys.favoriteReplies)
        defaults.removeObject(forKey: Keys.defaultTone)
        defaults.removeObject(forKey: Keys.recentMessages)
        objectWillChange.send()
    }
}
