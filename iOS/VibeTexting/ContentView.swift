//
//  ContentView.swift
//  VibeTexting
//
//  Main screen with voice input, tone selection, and AI response display.
//  This is the primary UI for the VibeTexting app.
//

import SwiftUI

struct ContentView: View {
    @StateObject private var voiceManager = VoiceInputManager()
    @EnvironmentObject private var apiManager: APIManager
    @EnvironmentObject private var storageManager: StorageManager
    
    /// The original message to reply to (from clipboard or manual input)
    @State private var originalMessage: String = ""
    
    /// Selected tone for the AI response
    @State private var selectedTone: Tone = .casual
    
    /// Generated AI response
    @State private var generatedResponse: String = ""
    
    /// Whether currently generating response
    @State private var isGenerating: Bool = false
    
    /// Show clipboard detection prompt
    @State private var showClipboardPrompt: Bool = false
    
    /// Show history view
    @State private var showHistory: Bool = false
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    // Original Message Section
                    originalMessageSection
                    
                    // Voice Input Section
                    voiceInputSection
                    
                    // Tone Selection Section
                    toneSelectionSection
                    
                    // Generate Button
                    generateButton
                    
                    // Generated Response Section
                    if !generatedResponse.isEmpty {
                        responseSection
                    }
                }
                .padding()
            }
            .navigationTitle("VibeTexting")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: { showHistory = true }) {
                        Image(systemName: "clock.fill")
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: checkClipboard) {
                        Image(systemName: "doc.on.clipboard")
                    }
                }
            }
            .sheet(isPresented: $showHistory) {
                HistoryView()
                    .environmentObject(storageManager)
            }
            .alert("Clipboard Message Detected", isPresented: $showClipboardPrompt) {
                Button("Use It", action: useClipboardMessage)
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Found a message on your clipboard. Would you like to use it?")
            }
        }
    }
    
    // MARK: - Subviews
    
    /// Section for displaying/editing the original message
    private var originalMessageSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Message to Reply To")
                .font(.headline)
                .foregroundColor(.secondary)
            
            TextField("Paste or type the message you received...",
                      text: $originalMessage,
                      axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...6)
            
            if originalMessage.isEmpty {
                HStack {
                    Image(systemName: "arrow.down.doc")
                        .foregroundColor(.secondary)
                    Text("Paste a message to get started")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }
    
    /// Section for voice input
    private var voiceInputSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your Reply (Optional)")
                .font(.headline)
                .foregroundColor(.secondary)
            
            VStack(spacing: 12) {
                // Microphone button
                Button(action: toggleRecording) {
                    ZStack {
                        Circle()
                            .fill(voiceManager.isRecording ? Color.red : Color.blue)
                            .frame(width: 80, height: 80)
                        
                        Image(systemName: voiceManager.isRecording ? "stop.fill" : "mic.fill")
                            .font(.title)
                            .foregroundColor(.white)
                    }
                }
                .disabled(!voiceManager.isAuthorized)
                
                // Status text
                Text(voiceManager.isRecording ? "Listening..." : "Tap to speak your reply")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                // Transcription display
                if !voiceManager.transcription.isEmpty {
                    Text(voiceManager.transcription)
                        .font(.body)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                }
                
                // Error display
                if let error = voiceManager.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                }
                
                // Authorization prompt
                if !voiceManager.isAuthorized {
                    Text("Speech recognition not authorized. Please enable in Settings.")
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
        }
    }
    
    /// Section for tone selection
    private var toneSelectionSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Choose Tone")
                .font(.headline)
                .foregroundColor(.secondary)
            
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                ForEach(Tone.allCases) { tone in
                    ToneButton(tone: tone, isSelected: selectedTone == tone)
                        .onTapGesture {
                            withAnimation(.spring()) {
                                selectedTone = tone
                            }
                        }
                }
            }
        }
    }
    
    /// Generate button
    private var generateButton: some View {
        Button(action: generateResponse) {
            HStack {
                if isGenerating {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                }
                Text(isGenerating ? "Generating..." : "Generate Reply")
                    .font(.headline)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(originalMessage.isEmpty ? Color.gray : Color.blue)
            .foregroundColor(.white)
            .cornerRadius(12)
        }
        .disabled(originalMessage.isEmpty || isGenerating)
    }
    
    /// Section for displaying generated response
    private var responseSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Generated Reply")
                .font(.headline)
                .foregroundColor(.secondary)
            
            VStack(spacing: 12) {
                Text(generatedResponse)
                    .font(.body)
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.systemBlue).opacity(0.1))
                    .cornerRadius(12)
                
                HStack(spacing: 12) {
                    // Copy button
                    Button(action: copyToClipboard) {
                        HStack {
                            Image(systemName: "doc.on.doc")
                            Text("Copy")
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(10)
                    }
                    
                    // Share button
                    Button(action: shareResponse) {
                        HStack {
                            Image(systemName: "square.and.arrow.up")
                            Text("Share")
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green)
                        .foregroundColor(.white)
                        .cornerRadius(10)
                    }
                }
            }
        }
    }
    
    // MARK: - Actions
    
    private func toggleRecording() {
        if voiceManager.isRecording {
            voiceManager.stopRecording()
        } else {
            voiceManager.startRecording()
        }
    }
    
    private func checkClipboard() {
        // Check if clipboard contains text
        if let clipboardText = UIPasteboard.general.string, !clipboardText.isEmpty {
            originalMessage = clipboardText
        }
    }
    
    private func useClipboardMessage() {
        if let clipboardText = UIPasteboard.general.string {
            originalMessage = clipboardText
        }
    }
    
    private func generateResponse() {
        print("DEBUG: generateResponse button clicked")
        Task { @MainActor in
            isGenerating = true
            
            do {
                let response = try await apiManager.generateReply(
                    originalMessage: originalMessage,
                    userReply: voiceManager.transcription.isEmpty ? nil : voiceManager.transcription,
                    tone: selectedTone
                )
                
                print("DEBUG: Updating UI with response: \(response.generatedReply)")
                generatedResponse = response.generatedReply
                
                // Save to history
                let generatedReply = GeneratedReply(
                    content: response.generatedReply,
                    tone: selectedTone
                )
                storageManager.saveReply(generatedReply)
                
            } catch {
                print("DEBUG: generateResponse failed with error: \(error)")
                generatedResponse = "Error: \(error.localizedDescription)"
            }
            
            isGenerating = false
        }
    }
    
    private func copyToClipboard() {
        UIPasteboard.general.string = generatedResponse
    }
    
    private func shareResponse() {
        // Present share sheet - in production, this would integrate with Messages, etc.
        let activityVC = UIActivityViewController(
            activityItems: [generatedResponse],
            applicationActivities: nil
        )
        
        // Find the window scene to present from
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let rootVC = windowScene.windows.first?.rootViewController {
            rootVC.present(activityVC, animated: true)
        }
    }
}

// MARK: - Tone Button Component

/// Reusable button for tone selection
struct ToneButton: View {
    let tone: Tone
    let isSelected: Bool
    
    var body: some View {
        VStack(spacing: 8) {
            Text(tone.icon)
                .font(.title2)
            Text(tone.rawValue)
                .font(.caption)
                .fontWeight(.medium)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(isSelected ? Color.blue : Color(.systemGray6))
        .foregroundColor(isSelected ? .white : .primary)
        .cornerRadius(10)
    }
}

#Preview {
    ContentView()
        .environmentObject(APIManager.shared)
}
