// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 949
    height: 593

    Timer {
        interval: 100
        running: true
        onTriggered: {
            window.liveTasks = [
                {"jobId": "1", "type": "library.scan", "state": "running",
                 "progress": {"current": 2, "total": 5}, "result": null,
                 "errorCode": null, "canCancel": true, "canRetry": false},
                {"jobId": "2", "type": "media.search", "state": "queued",
                 "progress": null, "result": null, "errorCode": null,
                 "canCancel": true, "canRetry": false},
                {"jobId": "3", "type": "content.import", "state": "succeeded",
                 "progress": {"current": 1, "total": 1}, "result": {},
                 "errorCode": null, "canCancel": false, "canRetry": false},
                {"jobId": "4", "type": "nsz.convert", "state": "failed",
                 "progress": null, "result": null, "errorCode": "E-CONTENT-CONVERT",
                 "canCancel": false, "canRetry": true},
                {"jobId": "5", "type": "steam.publish", "state": "cancelled",
                 "progress": null, "result": null, "errorCode": null,
                 "canCancel": false, "canRetry": true}
            ]
            window.responsiveTaskDrawer.open()
            captureTimer.start()
        }
    }

    Timer {
        id: captureTimer
        interval: window.motionDuration + 400
        onTriggered: window.responsiveTaskDrawer.contentItem.grabToImage(function(result) {
            Qt.exit(result.saveToFile("/tmp/steamzero-949x593-task-center.png") ? 0 : 1)
        })
    }
}
