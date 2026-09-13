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

const plugin=`package ${pkg};

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
                WebView webView = getBridge().getWebView();
                PrintManager printManager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                String jobName = call.getString("jobName", "PM POSHAN");
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

fs.writeFileSync(path.join(dir,'NativePrintPlugin.java'),plugin,'utf8');

if(main.endsWith('.java')){
  const replacement=`package ${pkg};

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(NativePrintPlugin.class);
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
        super.onCreate(savedInstanceState)
    }
}
`;
  if(original!==replacement)fs.writeFileSync(main,replacement,'utf8');
}

console.log(`ANDROID_NATIVE_PRINT_PATCH_OK (${path.relative(frontendRoot,main)})`);
