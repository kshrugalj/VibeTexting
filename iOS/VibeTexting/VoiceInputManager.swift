//
//  VoiceInputManager.swift
//  VibeTexting
//
//  Handles voice-to-text input using iOS Speech framework.
//  Manages speech recognition permissions and recording state.
//

import Foundation
import Speech

/// Manages voice input and speech recognition
@MainActor
class VoiceInputManager: ObservableObject {
    /// Current transcription from speech recognition
    @Published var transcription: String = ""
    
    /// Whether currently recording audio
    @Published var isRecording: Bool = false
    
    /// Whether speech recognition is authorized
    @Published var isAuthorized: Bool = false
    
    /// Error message if recognition fails
    @Published var errorMessage: String?
    
    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    
    init() {
        checkAuthorization()
        setupAudioSession()
    }
    
    /// Check speech and microphone authorization status
    func checkAuthorization() {
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            guard let self = self else { return }
            
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                Task { @MainActor in
                    self.isAuthorized = (status == .authorized && granted)
                    if !granted {
                        self.errorMessage = "Microphone access denied"
                    } else if status != .authorized {
                        self.errorMessage = "Speech recognition access denied"
                    }
                }
            }
        }
    }
    
    private func setupAudioSession() {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playAndRecord, mode: .measurement, options: .defaultToSpeaker)
            // No need to setActive here, we do it in startRecording
        } catch {
            print("Failed to setup audio session: \(error)")
        }
    }
    
    /// Start recording and speech recognition
    func startRecording() {
        guard isAuthorized else {
            errorMessage = "Speech recognition not authorized"
            return
        }
        
        guard !isRecording else { return }
        
        // Reset state
        transcription = ""
        errorMessage = nil
        
        // Cancel any existing task
        recognitionTask?.cancel()
        recognitionTask = nil
        
        do {
            // Configure audio session
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
            
            // Create recognition request
            recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
            guard let recognitionRequest = recognitionRequest else {
                errorMessage = "Unable to create recognition request"
                return
            }
            
            recognitionRequest.shouldReportPartialResults = true
            
            // Configure recognition task
            recognitionTask = speechRecognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
                guard let self = self else { return }
                
                Task { @MainActor in
                    if let error = error {
                        // Ignore cancellation errors
                        if (error as NSError).code != 301 {
                            self.errorMessage = error.localizedDescription
                            self.stopRecording()
                        }
                        return
                    }
                    
                    if let result = result {
                        self.transcription = result.bestTranscription.formattedString
                    }
                }
            }
            
            // Configure audio engine
            let inputNode = audioEngine.inputNode
            let recordingFormat = inputNode.outputFormat(forBus: 0)
            
            // Check if recording format is valid
            guard recordingFormat.sampleRate > 0 else {
                errorMessage = "Invalid audio input format"
                stopRecording()
                return
            }
            
            inputNode.removeTap(onBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, when in
                self?.recognitionRequest?.append(buffer)
            }
            
            audioEngine.prepare()
            try audioEngine.start()
            
            isRecording = true
        } catch {
            errorMessage = "Audio engine error: \(error.localizedDescription)"
            stopRecording()
        }
    }
    
    /// Stop recording and speech recognition
    func stopRecording() {
        guard isRecording else { return }
        
        isRecording = false
        
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        
        recognitionRequest?.endAudio()
        recognitionTask?.finish()
        
        recognitionRequest = nil
        recognitionTask = nil
        
        // Deactivate audio session
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            print("Failed to deactivate audio session: \(error)")
        }
    }
}
