//
//  ClipboardManager.swift
//  VibeTexting
//
//  Handles clipboard detection for automatically loading messages.
//  Monitors the clipboard for new text content.
//

import Foundation
import UIKit

/// Monitors clipboard for message content
@MainActor
class ClipboardManager: ObservableObject {
    /// Whether clipboard contains detectable text
    @Published var hasClipboardText: Bool = false
    
    /// Current clipboard content
    @Published var clipboardContent: String?
    
    private var timer: Timer?
    
    init() {
        startMonitoring()
    }
    
    /// Start monitoring clipboard changes
    func startMonitoring() {
        checkClipboard()
        
        // Poll clipboard every 2 seconds
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.checkClipboard()
            }
        }
    }
    
    /// Stop monitoring clipboard
    func stopMonitoring() {
        timer?.invalidate()
        timer = nil
    }
    
    /// Check clipboard for new content
    func checkClipboard() {
        guard let content = UIPasteboard.general.string, !content.isEmpty else {
            hasClipboardText = false
            clipboardContent = nil
            return
        }
        
        // Only trigger if content changed
        if clipboardContent != content {
            clipboardContent = content
            hasClipboardText = true
        }
    }
    
    /// Get clipboard content manually
    func getContent() -> String? {
        return UIPasteboard.general.string
    }
    
    /// Clear clipboard state (not the actual clipboard)
    func clearState() {
        hasClipboardText = false
    }
}
