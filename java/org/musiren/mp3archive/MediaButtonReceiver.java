package org.musiren.mp3archive;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.view.KeyEvent;

/**
 * Manifest-declared receiver for hardware media buttons (Bluetooth AVRCP and
 * wired headset).
 *
 * Media buttons reach an app only through an active MediaSession or through a
 * manifest receiver its media-button PendingIntent points at. The audio
 * service creates its session only while running, so after a reboot — no
 * process, no session — a Bluetooth play press had nowhere to go. This
 * receiver is that always-present target: the service wires it via
 * MediaSession.setMediaButtonReceiver so the framework routes buttons here
 * whenever the session is inactive, including when the process is gone.
 *
 * It maps the KeyEvent to the app's transport action and hands it to
 * {@link PlaybackLauncher}, which relays to a live service or cold-starts one
 * on the saved queue. Unlike the widget receiver this DOES carry a
 * MEDIA_BUTTON intent filter: that system action is never broadcast within
 * the app, so there is no double-handling risk, and an active session takes
 * priority over the manifest receiver anyway.
 */
public class MediaButtonReceiver extends BroadcastReceiver {

    private static final String PKG = "org.musiren.mp3archive";

    private static String actionFor(int keyCode) {
        switch (keyCode) {
            case KeyEvent.KEYCODE_MEDIA_PLAY:
            case KeyEvent.KEYCODE_MEDIA_PAUSE:
            case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE:
            case KeyEvent.KEYCODE_HEADSETHOOK:
                return PKG + ".TOGGLE";
            case KeyEvent.KEYCODE_MEDIA_NEXT:
            case KeyEvent.KEYCODE_MEDIA_FAST_FORWARD:
                return PKG + ".NEXT";
            case KeyEvent.KEYCODE_MEDIA_PREVIOUS:
            case KeyEvent.KEYCODE_MEDIA_REWIND:
                return PKG + ".PREV";
            case KeyEvent.KEYCODE_MEDIA_STOP:
                return PKG + ".STOP";
            default:
                return null;
        }
    }

    @Override
    public void onReceive(Context ctx, Intent intent) {
        if (intent == null
                || !Intent.ACTION_MEDIA_BUTTON.equals(intent.getAction())) {
            return;
        }
        KeyEvent event = intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT);
        // A press delivers ACTION_DOWN then ACTION_UP; act on DOWN only so a
        // single press is not handled twice.
        if (event == null || event.getAction() != KeyEvent.ACTION_DOWN) {
            return;
        }
        String action = actionFor(event.getKeyCode());
        if (action != null) {
            PlaybackLauncher.dispatch(ctx, action);
        }
    }
}
