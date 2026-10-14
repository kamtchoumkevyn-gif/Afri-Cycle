package cm.africycle.app;

import android.net.Uri;

import java.util.Locale;

/** The one website this app shows. Links anywhere else open outside the app. */
final class Site {
    static final String HOST = "afri-cycle.onrender.com";
    static final Uri START = Uri.parse("https://" + HOST + "/");

    private Site() {
    }

    /**
     * Whether a link is Africycle's own: https, this host, the standard port. The whole
     * authority (the part between "//" and the path) is compared, not just the host Android
     * finds in it, so tricks such as https://evil.example\@afri-cycle.onrender.com/ (which a
     * browser reads as evil.example) or a user name in the link are refused.
     */
    static boolean isOurs(Uri uri) {
        if (uri == null || !"https".equalsIgnoreCase(uri.getScheme())) {
            return false;
        }
        String authority = uri.getEncodedAuthority();
        if (authority == null) {
            return false;
        }
        authority = authority.toLowerCase(Locale.ROOT);
        return authority.equals(HOST) || authority.equals(HOST + ":443");
    }

    static boolean isOurs(String url) {
        return url != null && isOurs(Uri.parse(url));
    }
}
