package org.musiren.mp3archive;

import android.content.Context;
import android.content.Intent;
import android.media.session.MediaSession;

/**
 * Bridges lock-screen / system media-control transport events to the Python
 * audio service.
 *
 * On Android 13+ the lock-screen media card and headset/Bluetooth transport
 * buttons invoke {@link MediaSession.Callback} on the app's MediaSession.
 * That callback is an abstract class, so it cannot be implemented from Python
 * with pyjnius (which only implements interfaces). This tiny Java subclass
 * forwards each transport event as a broadcast Intent that the service's
 * already-registered BroadcastReceiver handles — the same path the
 * notification action buttons use.
 */
public class MediaSessionCallback extends MediaSession.Callback {

    private static final String PKG = "org.musiren.mp3archive";

    private final Context context;

    public MediaSessionCallback(Context context) {
        this.context = context;
    }

    private void send(String action) {
        Intent intent = new Intent(action);
        intent.setPackage(PKG);
        context.sendBroadcast(intent);
    }

    @Override
    public void onPlay() {
        // The card shows a single play/pause control; toggle matches its state.
        send(PKG + ".TOGGLE");
    }

    @Override
    public void onPause() {
        send(PKG + ".TOGGLE");
    }

    @Override
    public void onSkipToNext() {
        send(PKG + ".NEXT");
    }

    @Override
    public void onSkipToPrevious() {
        send(PKG + ".PREV");
    }

    @Override
    public void onStop() {
        send(PKG + ".STOP");
    }
}
