import BackgroundTasks

/// Background refresh: iOS decides when this actually runs (can be hours). The ~30 s budget is
/// too short for more than one upload, so each run processes at most one screenshot.
enum BackgroundRefresh {
    static let identifier = "com.snapsort.refresh"

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: nil) { task in
            BackgroundRefresh.schedule()
            let work = Task { @MainActor in
                await Agent.shared.scan(limit: 1)
                task.setTaskCompleted(success: true)
            }
            task.expirationHandler = {
                work.cancel()
                task.setTaskCompleted(success: false)
            }
        }
    }

    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }
}
