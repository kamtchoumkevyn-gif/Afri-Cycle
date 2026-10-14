package cm.africycle.app;

import com.google.androidbrowserhelper.locationdelegation.LocationDelegationExtraCommandHandler;

/**
 * The browser showing the app connects here to show Africycle's notifications (new chat
 * messages) as this app's, with its icon, and to ask this app for the phone's location, so
 * both permissions are found in Settings > Apps > Africycle. The library only lets in the
 * browser that opened the app, checked by its signing certificate.
 */
public class DelegationService extends com.google.androidbrowserhelper.trusted.DelegationService {
    @Override
    public void onCreate() {
        super.onCreate();
        registerExtraCommandHandler(new LocationDelegationExtraCommandHandler());
    }
}
