package com.gpcombine.assistant.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

/** 申请哪几个：按用户要求三件套全要（31+ 还要定位，虽然它不再必需）。 */
private fun permissionsToRequest(): Array<String> =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_CONNECT,
            Manifest.permission.ACCESS_FINE_LOCATION,
        )
    } else {
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }

/** 拦不拦人：只认真正必需的。31+ 拒绝了定位权限不该挡住 App。 */
private fun hasRequiredPermissions(ctx: Context): Boolean {
    val required = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    } else {
        listOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    return required.all {
        ContextCompat.checkSelfPermission(ctx, it) == PackageManager.PERMISSION_GRANTED
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val useFake = intent?.getBooleanExtra("fake", false) == true

        setContent {
            GPCombineTheme {
                val ctx = LocalContext.current
                var granted by remember { mutableStateOf(hasRequiredPermissions(ctx)) }
                val launcher = rememberLauncherForActivityResult(
                    ActivityResultContracts.RequestMultiplePermissions(),
                ) { granted = hasRequiredPermissions(ctx) }

                if (!granted) {
                    PermissionScreen(onRequest = { launcher.launch(permissionsToRequest()) })
                } else {
                    val vm: DeviceViewModel = viewModel(
                        factory = DeviceViewModel.factory(application, useFake),
                    )
                    val ui by vm.ui.collectAsStateWithLifecycle()
                    ConnectScreen(
                        ui = ui,
                        onScan = vm::startScan,
                        onConnect = vm::connect,
                        onCode = vm::submitCode,
                    )
                }
            }
        }
    }
}
