package cm.africycle.app;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Insets;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Parcelable;
import android.provider.MediaStore;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.GeolocationPermissions;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

import androidx.annotation.RequiresApi;
import androidx.core.content.FileProvider;

import java.io.File;
import java.io.IOException;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Africycle in the phone's WebView, for phones without a browser that can open the app full
 * screen. It is locked down like a browser:
 * <ul>
 *   <li>only https://afri-cycle.onrender.com opens here. Other links open in the phone's
 *       browser or the right app (maps, phone calls), and every other kind of link is refused;
 *   <li>a certificate problem stops the page (never "continue anyway"), and the https page
 *       can't load anything over plain http;
 *   <li>the page can't read the phone's files and gets no Java objects to call;
 *   <li>Google Safe Browsing checks every page (Android 8.0 and newer);
 *   <li>nothing is copied to backups (res/xml/data_extraction_rules.xml).
 * </ul>
 * It gives the page what a browser would: the location (Android asks the first time a map
 * needs it), photos from the camera or gallery, phone calls and maps, the back button and
 * gesture, room for notches and system bars, and a fresh page if the WebView crashes.
 */
public class WebAppActivity extends Activity {
    /**
     * Oldest WebView that runs the site: its scripts use async functions and the ** operator
     * (see frontend/js/probe.js), which Chrome and WebView have had since version 55.
     */
    static final int MIN_WEBVIEW_VERSION = 55;
    private static final Pattern CHROME_VERSION = Pattern.compile("Chrome/(\\d+)");
    private static final String FILE_PROVIDER = "cm.africycle.app.fileprovider";
    private static final int REQUEST_LOCATION = 1;
    private static final int REQUEST_FILES = 2;
    private static final int PHOTO_GRANT =
            Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    private static final String STATE_PAGE = "page";
    private static final String STATE_URL = "url";
    private static final String STATE_PHOTO = "photo";

    private ViewGroup content;
    private View statusBarBackground;
    private View splash;
    private ProgressBar progress;
    private View message;
    private TextView messageText;
    private Button messageButton;

    private WebView webView;
    private String lastUrl;

    private String locationOrigin;
    private GeolocationPermissions.Callback locationCallback;
    private ValueCallback<Uri[]> filesCallback;
    private File photoFile;
    private Uri photoUri;

    /** OnBackInvokedCallback on Android 13 and newer (kept as Object so older phones never load it). */
    private Object backCallback;
    private boolean backCallbackRegistered;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_web_app);
        content = findViewById(R.id.content);
        statusBarBackground = findViewById(R.id.status_bar_background);
        splash = findViewById(R.id.splash);
        progress = findViewById(R.id.progress);
        message = findViewById(R.id.message);
        messageText = findViewById(R.id.message_text);
        messageButton = findViewById(R.id.message_button);
        if (Build.VERSION.SDK_INT >= 35) {
            fitAroundSystemBars();
        }

        String url = Site.START.toString();
        Bundle page = null;
        if (savedInstanceState != null) {
            page = savedInstanceState.getBundle(STATE_PAGE);
            url = pick(savedInstanceState.getString(STATE_URL), url);
            String photo = savedInstanceState.getString(STATE_PHOTO);
            if (photo != null) {
                photoFile = new File(photo);
            }
        } else {
            deleteOldPhotos();
            url = pick(getIntent().getDataString(), url);
        }
        startWebView(url, page);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // An Africycle link opened while this screen was already showing
        String url = intent.getDataString();
        if (webView != null && Site.isOurs(url)) {
            hideMessage();
            webView.loadUrl(url);
        }
    }

    private static String pick(String url, String otherwise) {
        return Site.isOurs(url) ? url : otherwise;
    }

    // ---- The WebView ----

    private void startWebView(String url, Bundle savedPage) {
        lastUrl = url;
        if (webViewVersion() < MIN_WEBVIEW_VERSION) {
            showWebViewUpdate();
            return;
        }
        try {
            webView = new WebView(this);
        } catch (RuntimeException e) {
            // Android System WebView is missing, turned off, or being updated right now
            showWebViewUpdate();
            return;
        }
        content.addView(webView, 0, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        configure(webView);
        if (savedPage == null || webView.restoreState(savedPage) == null) {
            webView.loadUrl(url);
        }
    }

    /** The WebView's major version (the NN of "Chrome/NN" in its user agent); 0 when there is none. */
    private int webViewVersion() {
        try {
            Matcher found = CHROME_VERSION.matcher(WebSettings.getDefaultUserAgent(this));
            return found.find() ? Integer.parseInt(found.group(1)) : 0;
        } catch (RuntimeException e) {
            return 0;
        }
    }

    @SuppressLint("SetJavaScriptEnabled") // the site is a JavaScript app; it can only ever be our own https site
    private void configure(WebView view) {
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true); // the login and chosen language are kept in localStorage
        settings.setGeolocationEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false); // links that open a new tab load here, then go through the checks below
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setBuiltInZoomControls(true); // pinch to zoom, as in a browser
        settings.setDisplayZoomControls(false);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        if (Build.VERSION.SDK_INT >= 26) {
            settings.setSafeBrowsingEnabled(true);
        }
        // Lets the site recognise the app (to word its help for it, and not offer the app download)
        settings.setUserAgentString(settings.getUserAgentString() + " AfricycleApp/" + BuildConfig.VERSION_NAME);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(view, false);
        WebView.setWebContentsDebuggingEnabled((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0);

        view.setBackgroundColor(pageColor());
        view.setWebViewClient(new PageClient());
        view.setWebChromeClient(new BrowserFeatures());
        view.setDownloadListener((url, userAgent, contentDisposition, mimeType, length) ->
                openOutside(Uri.parse(url)));
    }

    @SuppressWarnings("deprecation") // getColor(int) without a theme: the only one before Android 6.0
    private int pageColor() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                ? getColor(R.color.page_background)
                : getResources().getColor(R.color.page_background);
    }

    /** Decides where each link opens, and handles pages that can't load. */
    private final class PageClient extends WebViewClient {
        @RequiresApi(Build.VERSION_CODES.N)
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return keepOutOfApp(request.getUrl(), request.isForMainFrame());
        }

        @SuppressWarnings("deprecation") // Android 5.0 to 6.0
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return keepOutOfApp(Uri.parse(url), true);
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            if (Site.isOurs(url)) {
                lastUrl = url;
            }
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            splash.setVisibility(View.GONE);
            updateBackHandling();
        }

        @Override
        public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {
            updateBackHandling();
        }

        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
            handler.cancel(); // never continue past a certificate problem
            if (Site.isOurs(error.getUrl())) {
                showConnectionProblem();
            }
        }

        @RequiresApi(Build.VERSION_CODES.M)
        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showConnectionProblem();
            }
        }

        @SuppressWarnings("deprecation") // Android 5.0 to 5.1 (only called for the page itself)
        @Override
        public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                showConnectionProblem();
            }
        }

        @RequiresApi(Build.VERSION_CODES.O)
        @Override
        public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            // The page's process crashed, or Android stopped it to free memory: start a fresh
            // WebView on the same page instead of letting the whole app close
            if (view == webView) {
                content.removeView(webView);
                webView.destroy();
                webView = null;
                startWebView(lastUrl, null);
            }
            return true;
        }
    }

    /**
     * Returns true when the WebView must not open the link itself: another website (opened in
     * the phone's browser or app), a phone number (the dialler, number ready: no permission
     * needed), or anything else (refused: intent:, file:, javascript:...).
     */
    private boolean keepOutOfApp(Uri link, boolean wholePage) {
        if (Site.isOurs(link)) {
            return false;
        }
        if (!wholePage) {
            return true; // frames from other sites: the app has none, so none are allowed
        }
        String scheme = link.getScheme() == null ? "" : link.getScheme().toLowerCase(Locale.ROOT);
        switch (scheme) {
            case "https":
            case "http":
                openOutside(link);
                break;
            case "tel":
                start(new Intent(Intent.ACTION_DIAL, link));
                break;
            case "mailto":
            case "sms":
            case "smsto":
                start(new Intent(Intent.ACTION_SENDTO, link));
                break;
            case "geo":
                start(new Intent(Intent.ACTION_VIEW, link));
                break;
            default:
                break;
        }
        return true;
    }

    private void openOutside(Uri link) {
        String scheme = link.getScheme() == null ? "" : link.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("https") && !scheme.equals("http")) {
            return;
        }
        Intent intent = new Intent(Intent.ACTION_VIEW, link);
        intent.addCategory(Intent.CATEGORY_BROWSABLE);
        start(intent);
    }

    private void start(Intent intent) {
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException | SecurityException e) {
            // No app on this phone for it: nothing to open
        }
    }

    // ---- What a browser gives a page ----

    private final class BrowserFeatures extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            progress.setProgress(newProgress);
            progress.setVisibility(newProgress < 100 ? View.VISIBLE : View.GONE);
        }

        @Override
        public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
            if (!Site.isOurs(origin)) {
                callback.invoke(origin, false, false);
            } else if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                callback.invoke(origin, true, false); // Android 5: allowed when the app was installed
            } else if (hasLocationPermission()) {
                callback.invoke(origin, true, false);
            } else {
                if (locationCallback != null) {
                    locationCallback.invoke(locationOrigin, false, false);
                }
                locationOrigin = origin;
                locationCallback = callback;
                requestPermissions(new String[] {Manifest.permission.ACCESS_FINE_LOCATION,
                        Manifest.permission.ACCESS_COARSE_LOCATION}, REQUEST_LOCATION);
            }
        }

        @Override
        public void onGeolocationPermissionsHidePrompt() {
            locationCallback = null;
        }

        @Override
        public void onPermissionRequest(PermissionRequest request) {
            request.deny(); // camera and microphone for calls: the site doesn't use them
        }

        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (filesCallback != null) {
                filesCallback.onReceiveValue(null);
            }
            filesCallback = callback;
            Intent camera = acceptsImages(params) ? cameraIntent() : null;
            Intent chooser;
            if (camera != null && params.isCaptureEnabled()) {
                chooser = camera; // <input capture>: straight to the camera
            } else {
                Intent pick;
                try {
                    pick = params.createIntent();
                } catch (RuntimeException e) {
                    pick = new Intent(Intent.ACTION_GET_CONTENT).addCategory(Intent.CATEGORY_OPENABLE).setType("image/*");
                }
                chooser = Intent.createChooser(pick, null);
                if (camera != null) {
                    chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Parcelable[] {camera});
                }
            }
            try {
                startActivityForResult(chooser, REQUEST_FILES);
            } catch (ActivityNotFoundException e) {
                deliverFiles(null);
            }
            return true;
        }
    }

    @RequiresApi(Build.VERSION_CODES.M)
    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_LOCATION || locationCallback == null) {
            return;
        }
        boolean allowed = false; // precise or approximate: either is enough for the map
        for (int result : grantResults) {
            allowed |= result == PackageManager.PERMISSION_GRANTED;
        }
        locationCallback.invoke(locationOrigin, allowed, false);
        locationCallback = null;
    }

    private static boolean acceptsImages(WebChromeClient.FileChooserParams params) {
        String[] types = params.getAcceptTypes();
        if (types == null || types.length == 0) {
            return true;
        }
        for (String type : types) {
            if (type == null || type.isEmpty() || type.startsWith("image/") || type.startsWith(".jp")
                    || type.equals(".png") || type.equals("*/*")) {
                return true;
            }
        }
        return false;
    }

    /** The phone's camera app, saving the photo where this app can hand it to the page; null when there is none. */
    private Intent cameraIntent() {
        Intent capture = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        if (capture.resolveActivity(getPackageManager()) == null) {
            return null;
        }
        try {
            File folder = new File(getCacheDir(), "camera");
            if (!folder.isDirectory() && !folder.mkdirs()) {
                return null;
            }
            photoFile = File.createTempFile("photo-", ".jpg", folder);
            photoUri = FileProvider.getUriForFile(this, FILE_PROVIDER, photoFile);
        } catch (IOException | IllegalArgumentException e) {
            return null;
        }
        capture.putExtra(MediaStore.EXTRA_OUTPUT, photoUri);
        capture.setClipData(ClipData.newRawUri("", photoUri));
        capture.addFlags(PHOTO_GRANT);
        // Picked from the chooser, the camera app may not receive the grant above: give it
        // directly to each camera app, for this one file only, and take it back afterwards
        for (ResolveInfo app : getPackageManager().queryIntentActivities(capture, PackageManager.MATCH_DEFAULT_ONLY)) {
            grantUriPermission(app.activityInfo.packageName, photoUri, PHOTO_GRANT);
        }
        return capture;
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_FILES) {
            return;
        }
        Uri[] chosen = null;
        if (resultCode == RESULT_OK) {
            chosen = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            boolean photoTaken = photoFile != null && photoFile.length() > 0;
            if ((chosen == null || chosen.length == 0) && photoTaken) {
                Uri photo = photoUri != null ? photoUri : FileProvider.getUriForFile(this, FILE_PROVIDER, photoFile);
                chosen = new Uri[] {photo};
            }
        }
        if (photoUri != null) {
            revokeUriPermission(photoUri, PHOTO_GRANT);
        }
        deliverFiles(chosen);
    }

    private void deliverFiles(Uri[] files) {
        if (filesCallback != null) {
            filesCallback.onReceiveValue(files); // null tells the page nothing was chosen
            filesCallback = null;
        }
    }

    /** Photos taken in earlier sessions have been read by the page long ago. */
    private void deleteOldPhotos() {
        File[] photos = new File(getCacheDir(), "camera").listFiles();
        if (photos != null) {
            for (File photo : photos) {
                //noinspection ResultOfMethodCallIgnored
                photo.delete();
            }
        }
    }

    // ---- Messages: no connection, or a WebView too old ----

    private void showConnectionProblem() {
        showMessage(R.string.server_unreachable, R.string.try_again, button -> {
            hideMessage();
            if (webView == null) {
                startWebView(lastUrl, null);
            } else if (webView.getUrl() == null || !Site.isOurs(webView.getUrl())) {
                webView.loadUrl(lastUrl);
            } else {
                webView.reload();
            }
        });
    }

    private void showWebViewUpdate() {
        showMessage(R.string.webview_too_old, R.string.update, button -> openStore(webViewPackage()));
    }

    private void showMessage(int text, int action, View.OnClickListener onAction) {
        splash.setVisibility(View.GONE);
        progress.setVisibility(View.GONE);
        messageText.setText(text);
        messageButton.setText(action);
        messageButton.setOnClickListener(onAction);
        message.setVisibility(View.VISIBLE);
    }

    private void hideMessage() {
        message.setVisibility(View.GONE);
    }

    @SuppressLint("WebViewApiAvailability") // the platform's own call, from Android 8.0; before, the usual package
    private String webViewPackage() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            PackageInfo current = WebView.getCurrentWebViewPackage();
            if (current != null) {
                return current.packageName;
            }
        }
        return "com.google.android.webview";
    }

    private void openStore(String packageName) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + packageName)));
        } catch (ActivityNotFoundException e) {
            openOutside(Uri.parse("https://play.google.com/store/apps/details?id=" + packageName));
        }
    }

    // ---- Back button and gesture ----

    @SuppressWarnings("deprecation") // Android 12L and older; newer ones use updateBackHandling()
    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /**
     * Android 13 and newer: "back" goes to the previous page while there is one; on the first
     * page it leaves the app, with the system's animation (predictive back).
     */
    private void updateBackHandling() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            setBackCallback(webView != null && webView.canGoBack());
        }
    }

    @RequiresApi(Build.VERSION_CODES.TIRAMISU)
    private void setBackCallback(boolean wanted) {
        if (wanted == backCallbackRegistered) {
            return;
        }
        if (backCallback == null) {
            backCallback = (OnBackInvokedCallback) () -> {
                if (webView != null && webView.canGoBack()) {
                    webView.goBack();
                }
            };
        }
        OnBackInvokedDispatcher dispatcher = getOnBackInvokedDispatcher();
        if (wanted) {
            dispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    (OnBackInvokedCallback) backCallback);
        } else {
            dispatcher.unregisterOnBackInvokedCallback((OnBackInvokedCallback) backCallback);
        }
        backCallbackRegistered = wanted;
    }

    // ---- Notches and system bars (Android 15 and newer draw the app behind them) ----

    @RequiresApi(35)
    private void fitAroundSystemBars() {
        findViewById(R.id.root).setOnApplyWindowInsetsListener((root, insets) -> {
            Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            Insets keyboard = insets.getInsets(WindowInsets.Type.ime());
            FrameLayout.LayoutParams area = (FrameLayout.LayoutParams) content.getLayoutParams();
            area.setMargins(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
            content.setLayoutParams(area);
            ViewGroup.LayoutParams statusBar = statusBarBackground.getLayoutParams();
            statusBar.height = bars.top;
            statusBarBackground.setLayoutParams(statusBar);
            return WindowInsets.CONSUMED;
        });
        // White status bar icons on the green, dark navigation icons on the light page
        WindowInsetsController bars = getWindow().getInsetsController();
        if (bars != null) {
            bars.setSystemBarsAppearance(WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                    WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                            | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
        }
    }

    // ---- Lifecycle ----

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.onPause();
            CookieManager.getInstance().flush();
        }
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putString(STATE_URL, lastUrl);
        if (webView != null) {
            Bundle page = new Bundle();
            webView.saveState(page);
            outState.putBundle(STATE_PAGE, page);
        }
        if (photoFile != null) {
            outState.putString(STATE_PHOTO, photoFile.getPath());
        }
    }

    @Override
    protected void onDestroy() {
        if (locationCallback != null) {
            locationCallback.invoke(locationOrigin, false, false);
            locationCallback = null;
        }
        deliverFiles(null);
        if (webView != null) {
            content.removeView(webView);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
