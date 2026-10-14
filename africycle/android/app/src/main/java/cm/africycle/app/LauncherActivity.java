package cm.africycle.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;

import androidx.browser.customtabs.CustomTabsCallback;

import com.google.androidbrowserhelper.trusted.TwaLauncher;

/**
 * The app's icon opens this screen. It shows https://afri-cycle.onrender.com full screen in a
 * browser that can (Chrome, Samsung Internet, Edge...): the browser reads the website's
 * /.well-known/assetlinks.json, which names the key this app is signed with, and only then
 * hides its address bar. Notifications and location are this app's own (DelegationService).
 * Phones without such a browser get WebAppActivity, the built-in screen.
 */
public class LauncherActivity extends com.google.androidbrowserhelper.trusted.LauncherActivity {

    private static final int GRANT_FLAGS = Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        // Any app may open this screen (it is the icon, and Africycle links open it), so only
        // the safe part of what they send is kept: an Africycle link. Other websites, files
        // (content://), extras and permission grants are dropped before anything reads them.
        setIntent(safeCopy(getIntent()));
        super.onCreate(savedInstanceState);
    }

    static Intent safeCopy(Intent received) {
        Uri link = received.getData();
        boolean ours = Site.isOurs(link);
        Intent safe = new Intent(ours ? Intent.ACTION_VIEW : Intent.ACTION_MAIN);
        safe.setComponent(received.getComponent());
        if (ours) {
            safe.setData(link);
        }
        safe.setFlags(received.getFlags() & ~GRANT_FLAGS);
        return safe;
    }

    @Override
    protected Uri getLaunchingUrl() {
        Uri url = super.getLaunchingUrl();
        return Site.isOurs(url) ? url : Site.START;
    }

    @Override
    protected TwaLauncher.FallbackStrategy getFallbackStrategy() {
        return (context, builder, providerPackage, completionCallback) -> {
            Intent intent = new Intent(context, WebAppActivity.class);
            intent.setData(builder.getUri());
            // An Africycle link opened while the app is already showing loads in the same screen
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            context.startActivity(intent);
            if (completionCallback != null) {
                completionCallback.run();
            }
        };
    }

    @Override
    protected CustomTabsCallback getCustomTabsCallback() {
        // The library's default (QualityEnforcer) closes the app on purpose when the browser
        // reports a "quality" problem, such as a page that didn't load while the server was
        // waking up. People see the page's own message instead.
        return new CustomTabsCallback();
    }
}
