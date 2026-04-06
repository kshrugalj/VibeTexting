//
//  VibeTextingApp.swift
//  VibeTexting
//
//  Main entry point for the VibeTexting iOS app.
//  This app helps users respond to text messages faster using AI.
//

import SwiftUI

@main
struct VibeTextingApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(APIManager.shared)
                .environmentObject(StorageManager.shared)
        }
    }
}
