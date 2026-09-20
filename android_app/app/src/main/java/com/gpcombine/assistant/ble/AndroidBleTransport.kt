package com.gpcombine.assistant.ble

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat
import com.gpcombine.assistant.proto.Frame
import com.gpcombine.assistant.proto.FrameParser
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

data class ScannedDevice(val name: String, val address: String, val rssi: Int)

class AndroidBleTransport(private val context: Context) : BleTransport {
    companion object {
        // Nordic UART Service：手机端不写自定义服务也能用 nRF Connect 手测，固件侧同一套 UUID
        val SERVICE: UUID = UUID.fromString("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        val RX: UUID = UUID.fromString("6E400002-B5A3-F393-E0A9-E50E24DCCA9E") // 手机 → 设备（写）
        val TX: UUID = UUID.fromString("6E400003-B5A3-F393-E0A9-E50E24DCCA9E") // 设备 → 手机（订阅）
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        const val NAME_PREFIX = "GP-Combine-"
        const val REQUEST_MTU = 247
        private const val ATT_HEADER = 3
    }

    private val _inbound = MutableSharedFlow<Frame>(extraBufferCapacity = 32)
    override val inbound: Flow<Frame> = _inbound.asSharedFlow()

    private val _state = MutableStateFlow(BleState.IDLE)
    override val state: StateFlow<BleState> = _state.asStateFlow()

    private val _log = MutableSharedFlow<String>(replay = 64, extraBufferCapacity = 64)
    override val log: Flow<String> = _log.asSharedFlow()

    private val main = Handler(Looper.getMainLooper())
    private val discoveryStarted = AtomicBoolean(false)

    private var gatt: BluetoothGatt? = null
    private var rxChar: BluetoothGattCharacteristic? = null
    private var mtu = 23
    private var parser = FrameParser()

    private fun note(s: String) {
        _log.tryEmit(s)
    }

    // ---- 权限 ----

    /** Android 12(31)+ 要「附近设备」，11 及以下扫 BLE 要定位。 */
    private fun missingPermissions(): List<String> {
        val needed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            listOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        return needed.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
    }

    private fun requirePermissions() {
        val missing = missingPermissions()
        check(missing.isEmpty()) { "缺少蓝牙权限：${missing.joinToString()}" }
    }

    private fun requireAdapter(): BluetoothAdapter {
        requirePermissions()
        val mgr = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        return mgr.adapter ?: error("这台手机没有蓝牙适配器")
    }

    // ---- 扫描 ----

    @SuppressLint("MissingPermission")
    fun scan(): Flow<ScannedDevice> = callbackFlow {
        val adapter = requireAdapter()
        check(adapter.isEnabled) { "蓝牙没打开" }
        val scanner = adapter.bluetoothLeScanner ?: error("拿不到 BLE 扫描器")

        val cb = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val name = result.device.name ?: return
                if (!name.startsWith(NAME_PREFIX)) return
                trySend(ScannedDevice(name, result.device.address, result.rssi))
            }
        }

        _state.value = BleState.SCANNING
        scanner.startScan(
            null,
            ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(),
            cb,
        )
        awaitClose {
            scanner.stopScan(cb)
            if (_state.value == BleState.SCANNING) _state.value = BleState.IDLE
        }
    }

    // ---- 连接 ----

    @SuppressLint("MissingPermission")
    suspend fun connect(address: String) {
        val adapter = requireAdapter()
        // 重连前先把上一个 BluetoothGatt 关掉：不关就一直占着一个 GATT client
        // （系统上限 32，反复"连上→断电→重连"会把配额耗光，之后 connectGatt 直接返回 null）。
        close()
        _state.value = BleState.CONNECTING
        parser = FrameParser()
        discoveryStarted.set(false)
        note("connect ${address.takeLast(5)}")
        val device = adapter.getRemoteDevice(address)
        gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
        if (gatt == null) {
            note("connectGatt 返回 null（GATT client 配额用光了？）")
            _state.value = BleState.IDLE
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            note("conn status=$status newState=$newState")
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                // 服务发现必须单独占住 GATT，不跟 requestMtu 抢（见 onServicesDiscovered 末尾）
                startDiscovery(g)
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                rxChar = null
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    note("断开 status=$status")
                }
                note("disconnected")
                gatt?.close()      // 断连后不 close 同样占着配额
                gatt = null
                _state.value = BleState.DISCONNECTED
            }
        }

        /** GATT 一次只能跑一个操作，所以发现服务这件事做成幂等的，谁先到谁触发。 */
        private fun startDiscovery(g: BluetoothGatt) {
            if (!discoveryStarted.compareAndSet(false, true)) return
            if (!g.discoverServices()) {
                note("discoverServices() 返回 false")
                _state.value = BleState.DISCONNECTED
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            note("svc status=$status")
            if (status != BluetoothGatt.GATT_SUCCESS) {
                _state.value = BleState.DISCONNECTED
                return
            }
            val svc = g.getService(SERVICE) ?: run {
                note("没找到 NUS 服务，设备只暴露了 ${g.services.map { it.uuid.toString().take(8) }}")
                _state.value = BleState.DISCONNECTED
                return
            }
            rxChar = svc.getCharacteristic(RX)
            val tx = svc.getCharacteristic(TX)
            if (rxChar == null || tx == null) {
                note("NUS 里没有 RX=$RX / TX=$TX")
                _state.value = BleState.DISCONNECTED
                return
            }
            // 不订阅 TX，设备的 notify 会一直失败，连续 20 次后整帧丢弃 —— 现象是"发出去没回包"
            g.setCharacteristicNotification(tx, true)
            val cccd = tx.getDescriptor(CCCD)
            if (cccd != null) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    g.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                } else {
                    @Suppress("DEPRECATION")
                    cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    g.writeDescriptor(cccd)
                }
            }
            g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
            _state.value = BleState.CONNECTED
            // MTU 放到订阅之后再要，避免它和服务发现互相抢 GATT；协商失败也只是分片变小
            main.postDelayed({ g.requestMtu(REQUEST_MTU) }, 300)
        }

        override fun onMtuChanged(g: BluetoothGatt, newMtu: Int, status: Int) {
            mtu = newMtu
            note("mtu=$newMtu status=$status")
        }

        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
            note("cccd write status=$status")
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) note("write status=$status")
        }

        @Deprecated("Android 13 起走新签名")
        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            ch: BluetoothGattCharacteristic,
        ) {
            @Suppress("DEPRECATION")
            feed(ch.value ?: return)
        }

        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            ch: BluetoothGattCharacteristic,
            value: ByteArray,
        ) {
            feed(value)
        }
    }

    /** 把一段 notify 数据喂给分片重组器，攒够一整帧才吐出去。 */
    private fun feed(bytes: ByteArray) {
        for (b in bytes) parser.push(b)?.let { _inbound.tryEmit(it) }
    }

    // ---- 发送 ----

    @SuppressLint("MissingPermission")
    override suspend fun send(frame: ByteArray) {
        val g = gatt ?: error("还没连上设备")
        val ch = rxChar ?: error("还没发现 RX 特征")
        val max = mtu - ATT_HEADER
        require(frame.size <= max) { "一帧 ${frame.size} 字节超过 MTU $mtu 能带的 $max 字节" }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            g.writeCharacteristic(
                ch, frame, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE,
            )
        } else {
            @Suppress("DEPRECATION")
            ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            @Suppress("DEPRECATION")
            ch.value = frame
            @Suppress("DEPRECATION")
            g.writeCharacteristic(ch)
        }
    }

    @SuppressLint("MissingPermission")
    fun close() {
        gatt?.close()
        gatt = null
        rxChar = null
        _state.value = BleState.IDLE
    }
}
