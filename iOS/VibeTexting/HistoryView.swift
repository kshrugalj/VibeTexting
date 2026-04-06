//
//  HistoryView.swift
//  VibeTexting
//
//  Displays history of generated replies.
//  Allows users to view, copy, or favorite past replies.
//

import SwiftUI

struct HistoryView: View {
    @EnvironmentObject private var storageManager: StorageManager
    @Environment(\.dismiss) private var dismiss
    
    @State private var replies: [GeneratedReply] = []
    @State private var showFavoritesOnly: Bool = false
    
    var displayedReplies: [GeneratedReply] {
        if showFavoritesOnly {
            return replies.filter { $0.isFavorite }
        }
        return replies
    }
    
    var body: some View {
        NavigationView {
            Group {
                if displayedReplies.isEmpty {
                    emptyStateView
                } else {
                    replyList
                }
            }
            .navigationTitle(showFavoritesOnly ? "Favorites" : "History")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Done") { dismiss() }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Picker("", selection: $showFavoritesOnly) {
                        Text("All").tag(false)
                        Text("Favorites").tag(true)
                    }
                    .pickerStyle(.segmented)
                }
            }
        }
        .onAppear {
            replies = storageManager.getReplyHistory()
        }
    }
    
    // MARK: - Subviews
    
    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Image(systemName: showFavoritesOnly ? "heart.slash" : "clock.badge.exclamationmark")
                .font(.system(size: 60))
                .foregroundColor(.secondary)
            
            Text(showFavoritesOnly ? "No Favorites Yet" : "No History")
                .font(.headline)
            
            Text(showFavoritesOnly ? "Favorite replies to save them here" : "Generated replies will appear here")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
    
    private var replyList: some View {
        List(displayedReplies) { reply in
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text(reply.tone.icon)
                    Text(reply.tone.rawValue)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Spacer()
                    
                    Text(reply.timestamp, style: .relative)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                
                Text(reply.content)
                    .font(.body)
                
                HStack(spacing: 12) {
                    Button(action: {
                        UIPasteboard.general.string = reply.content
                    }) {
                        Image(systemName: "doc.on.doc")
                        Text("Copy")
                    }
                    .buttonStyle(.bordered)
                    
                    Button(action: {
                        withAnimation {
                            storageManager.toggleFavorite(for: reply.id)
                            replies = storageManager.getReplyHistory()
                        }
                    }) {
                        Image(systemName: reply.isFavorite ? "heart.fill" : "heart")
                            .foregroundColor(reply.isFavorite ? .red : .primary)
                        Text(reply.isFavorite ? "Favorited" : "Favorite")
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }
}

#Preview {
    HistoryView()
        .environmentObject(StorageManager.shared)
}
