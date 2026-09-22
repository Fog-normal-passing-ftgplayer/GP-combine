package com.gpcombine.assistant.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.gpcombine.assistant.term.TermLine
import com.gpcombine.assistant.term.TermState

/**
 * 终端页：手打命令直接发帧。
 *
 * 输出不是这里自己记的，而是 DeviceClient 的帧流水（和诊断→帧监视器同一份），
 * 所以"终端里看到的"和"帧监视器里看到的"永远一致；不一样的地方只有：这里把回包
 * 翻译了成人话（pong / 认证通过 / 主题=翠绿…）。
 */
@Composable
fun TerminalScreen(state: TermState, onSend: (String) -> Unit, onClear: () -> Unit) {
    var input by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    LaunchedEffect(state.lines.size) {
        if (state.lines.isNotEmpty()) listState.scrollToItem(state.lines.size - 1)
    }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                label = { Text(if (state.busy) "上一条还在等回包…" else "命令（打 help 看用法）") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    autoCorrectEnabled = false,
                    capitalization = KeyboardCapitalization.None,
                    keyboardType = KeyboardType.Ascii,
                    imeAction = ImeAction.Send,
                ),
                keyboardActions = androidx.compose.foundation.text.KeyboardActions(
                    onSend = {
                        if (input.isNotBlank()) {
                            onSend(input)
                            input = ""
                        }
                    },
                ),
                modifier = Modifier.weight(1f),
            )
            Button(
                onClick = {
                    if (input.isNotBlank()) {
                        onSend(input)
                        input = ""
                    }
                },
            ) { Text("发送") }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            QUICK.forEach { q ->
                OutlinedButton(onClick = { onSend(q) }) { Text(q) }
            }
            OutlinedButton(onClick = onClear) { Text("清屏") }
        }

        state.lastCommand.takeIf { it.isNotEmpty() }?.let {
            Text("上一条：$it", style = MaterialTheme.typography.bodySmall)
        }

        LazyColumn(state = listState, modifier = Modifier.fillMaxSize()) {
            items(state.lines) { l -> TermRow(l) }
        }
    }
}

private val QUICK = listOf("ping", "info", "pair", "logs on", "logs off", "cfg get", "help")

@Composable
private fun TermRow(l: TermLine) {
    val color = when (l.kind) {
        TermLine.Kind.ECHO -> MaterialTheme.colorScheme.primary
        TermLine.Kind.ERR -> MaterialTheme.colorScheme.error
        TermLine.Kind.INFO -> MaterialTheme.colorScheme.onSurface
    }
    Text(
        text = l.text,
        color = color,
        style = MaterialTheme.typography.bodySmall,
        fontFamily = FontFamily.Monospace,
        modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp),
    )
}
