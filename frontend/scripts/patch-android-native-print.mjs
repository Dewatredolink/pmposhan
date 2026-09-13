import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const frontendRoot=path.resolve(here,'..');
const javaRoot=path.join(frontendRoot,'android','app','src','main','java');

function walk(dir){
  if(!fs.existsSync(dir))return [];
  const out=[];
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,entry.name);
    if(entry.isDirectory())out.push(...walk(p)); else out.push(p);
  }
  return out;
}

const main=walk(javaRoot).find(p=>/MainActivity\.(java|kt)$/.test(p));
if(!main){
  console.log('ANDROID_NATIVE_PRINT_PATCH_SKIPPED (generated Android project not present yet)');
  process.exit(0);
}

const original=fs.readFileSync(main,'utf8');
const packageMatch=original.match(/^package\s+([A-Za-z0-9_.]+)\s*;?/m);
if(!packageMatch)throw new Error(`Cannot determine Android package from ${main}`);
const pkg=packageMatch[1];
const dir=path.dirname(main);

const printPlugin=`package ${pkg};

import android.content.Context;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.webkit.WebView;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "NativePrint")
public class NativePrintPlugin extends Plugin {
    @PluginMethod
    public void print(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try {
                WebView webView = bridge.getWebView();
                PrintManager printManager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                String jobName = call.getString("jobName");
                if (jobName == null || jobName.trim().isEmpty()) jobName = "PM POSHAN";
                PrintDocumentAdapter adapter = webView.createPrintDocumentAdapter(jobName);
                printManager.print(jobName, adapter, new PrintAttributes.Builder().build());
                JSObject result = new JSObject();
                result.put("started", true);
                call.resolve(result);
            } catch (Exception error) {
                call.reject("ANDROID_PRINT_FAILED: " + error.getMessage(), error);
            }
        });
    }
}
`;

const filePlugin=`package ${pkg};

import android.content.ContentResolver;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

@CapacitorPlugin(name = "NativeFile")
public class NativeFilePlugin extends Plugin {
    private String safeName(String raw) {
        String name = raw == null ? "PM_POSHAN_Report" : raw.trim();
        name = name.replaceAll("[\\\\/:*?<>|]", "_").replace('"', '_');
        if (name.isEmpty()) name = "PM_POSHAN_Report";
        return name;
    }

    @PluginMethod
    public void save(PluginCall call) {
        try {
            String fileName = safeName(call.getString("fileName"));
            String mimeType = call.getString("mimeType");
            if (mimeType == null || mimeType.trim().isEmpty()) mimeType = "application/octet-stream";
            String base64 = call.getString("base64");
            if (base64 == null || base64.isEmpty()) {
                call.reject("ANDROID_FILE_SAVE_FAILED: missing file data");
                return;
            }
            byte[] data = Base64.decode(base64, Base64.DEFAULT);
            JSObject result = new JSObject();

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ContentResolver resolver = getContext().getContentResolver();
                ContentValues values = new ContentValues();
                values.put(MediaStore.Downloads.DISPLAY_NAME, fileName);
                values.put(MediaStore.Downloads.MIME_TYPE, mimeType);
                values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/PM_POSHAN");
                values.put(MediaStore.Downloads.IS_PENDING, 1);
                Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) throw new IllegalStateException("Could not create download entry");
                try (OutputStream out = resolver.openOutputStream(uri)) {
                    if (out == null) throw new IllegalStateException("Could not open download output stream");
                    out.write(data);
                    out.flush();
                } catch (Exception error) {
                    resolver.delete(uri, null, null);
                    throw error;
                }
                values.clear();
                values.put(MediaStore.Downloads.IS_PENDING, 0);
                resolver.update(uri, values, null, null);
                result.put("saved", true);
                result.put("uri", uri.toString());
                result.put("location", "Downloads/PM_POSHAN/" + fileName);
                call.resolve(result);
                return;
            }

            File base = getContext().getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
            if (base == null) base = getContext().getFilesDir();
            File folder = new File(base, "PM_POSHAN");
            if (!folder.exists() && !folder.mkdirs()) throw new IllegalStateException("Could not create download folder");
            File target = new File(folder, fileName);
            try (FileOutputStream out = new FileOutputStream(target)) {
                out.write(data);
                out.flush();
            }
            result.put("saved", true);
            result.put("uri", Uri.fromFile(target).toString());
            result.put("location", target.getAbsolutePath());
            call.resolve(result);
        } catch (Exception error) {
            call.reject("ANDROID_FILE_SAVE_FAILED: " + error.getMessage(), error);
        }
    }
}
`;

fs.writeFileSync(path.join(dir,'NativePrintPlugin.java'),printPlugin,'utf8');
fs.writeFileSync(path.join(dir,'NativeFilePlugin.java'),filePlugin,'utf8');

if(main.endsWith('.java')){
  const replacement=`package ${pkg};

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(NativePrintPlugin.class);
        registerPlugin(NativeFilePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
`;
  if(original!==replacement)fs.writeFileSync(main,replacement,'utf8');
}else{
  const replacement=`package ${pkg}

import android.os.Bundle
import com.getcapacitor.BridgeActivity

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(NativePrintPlugin::class.java)
        registerPlugin(NativeFilePlugin::class.java)
        super.onCreate(savedInstanceState)
    }
}
`;
  if(original!==replacement)fs.writeFileSync(main,replacement,'utf8');
}

console.log(`ANDROID_NATIVE_PRINT_PATCH_OK (${path.relative(frontendRoot,main)})`);
console.log('ANDROID_NATIVE_FILE_PATCH_OK');
