/* 爻语在线 IDE —— 前端主逻辑（原生 JS，零依赖，可离线）
 *
 * 后端契约见 SPEC.md 第 7 节：
 *   GET  /api/健康   GET /api/例   GET /api/谱
 *   POST /api/跑  {"码": "...", "参": []}
 *        → {"成": bool, "出": string, "错": null|{类,文,行,列,栈}, "耗": int}
 */
(function () {
  'use strict';

  var 存码键 = 'yao.码';
  var 示例默认 = '你好';
  var 行高 = 24.5;          // 与 style.css 的 --行高px 保持一致
  var 编上内边 = 12;        // 与 style.css 的 --编上下 保持一致（Js 兜底再读取实际值）

  /* ── DOM ─────────────────────────────────────────────── */
  var $ = function (id) { return document.getElementById(id); };

  var 代码框 = $('代码');
  var 高亮层 = $('高亮层');
  var 高亮码 = $('高亮码');
  var 行号栏 = $('行号栏');
  var 编辑区 = $('编辑区');
  var 行号位 = $('光标位');
  var 字数量 = $('字数');
  var 运行按钮 = $('运行按钮');
  var 清空按钮 = $('清空按钮');
  var 示例选择 = $('示例选择');
  var 标准输出 = $('标准输出');
  var 错误块 = $('错误块');
  var 错误类 = $('错误类');
  var 错误文 = $('错误文');
  var 错误定位 = $('错误定位');
  var 错误跳转文 = $('错误跳转文');
  var 调用栈区 = $('调用栈区');
  var 栈列 = $('栈列');
  var 提示块 = $('提示块');
  var 提示文本 = $('提示文本');
  var 运行状态 = $('运行状态');
  var 状态提示 = $('状态提示');
  var 耗时位 = $('耗时');
  var 后端状态 = $('后端状态');
  var 后端文本 = $('后端文本');
  var 版本号 = $('版本号');
  var 过滤输入 = $('过滤输入');
  var 速查内容 = $('速查内容');
  var 速查提示 = $('速查提示');
  var 标签们 = Array.prototype.slice.call(document.querySelectorAll('.标签'));
  var 页们 = { '输出': $('页-输出'), '速查': $('页-速查') };

  /* ── 状态 ─────────────────────────────────────────────── */
  var 谱 = null;              // /api/谱 数据
  var 例子 = [];              // /api/例 的 例子 数组
  var 运行中 = false;
  var 渲染排队 = false;

  /* ── 小工具 ───────────────────────────────────────────── */
  function 秒表() { return (window.performance && performance.now) ? performance.now() : Date.now(); }

  /* 把浏览器原生的英文网络错误翻成中文，界面里不出现英文技术噪音。 */
  function 中文错误(误, 默认) {
    var 文 = (误 && 误.message) ? String(误.message) : '';
    if (/Failed to fetch|NetworkError|Load failed/i.test(文)) return '网络请求失败';
    if (/aborted|AbortError/i.test(文)) return '请求被中止';
    if (/HTTP\s*(\d+)/i.test(文)) return '后端返回了错误状态（' + 文 + '）';
    return 文 || 默认 || '未知错误';
  }

  function 设置提示(文, 警告) {
    if (!文) {
      提示块.hidden = true;
      提示文本.textContent = '';
      return;
    }
    // 已有警告时不覆盖：先到的「后端不可达」比后到的次级失败更有意义
    if (警告 && !提示块.hidden && 提示块.classList.contains('警告')) return;
    提示文本.textContent = 文;
    提示块.hidden = false;
    提示块.classList.toggle('警告', !!警告);
  }

  function 设置后端(通, 文) {
    后端状态.classList.toggle('通', 通);
    后端状态.classList.toggle('断', !通);
    后端文本.textContent = 文;
    后端状态.title = 通 ? '后端已连接：' + 文 : '后端不可达：' + 文;
  }

  function 行数(文) {
    if (!文) return 1;
    var n = 1;
    for (var i = 0; i < 文.length; i++) if (文.charAt(i) === '\n') n++;
    return n;
  }

  function 当前行号(文, 位) {
    var 行 = 1;
    for (var i = 0; i < 位 && i < 文.length; i++) if (文.charAt(i) === '\n') 行++;
    return 行;
  }

  function 行首偏移(文, 行) {
    var 位 = 0;
    for (var i = 1; i < 行; i++) {
      var 下 = 文.indexOf('\n', 位);
      if (下 < 0) return 文.length;
      位 = 下 + 1;
    }
    return Math.min(位, 文.length);
  }

  /* 读取编辑器实际行高与内边距，保证与样式一致（防止后续改 CSS 后错位）。 */
  function 取度量() {
    var 算 = window.getComputedStyle(代码框);
    var 值 = parseFloat(算.lineHeight);
    if (!isNaN(值) && 值 > 0) 行高 = 值;
    var 上 = parseFloat(算.paddingTop);
    if (!isNaN(上)) 编上内边 = 上;
  }

  /* ── 编辑器：高亮 / 行号 / 滚动 ───────────────────────── */
  function 重绘行号() {
    var 文 = 代码框.value;
    var 数 = 行数(文);
    var 片段 = [];
    var 光行 = 当前行号(文, 代码框.selectionStart);
    for (var i = 1; i <= 数; i++) {
      片段.push('<div class="行号' + (i === 光行 ? ' 当前' : '') + '">' + i + '</div>');
    }
    行号栏.innerHTML = 片段.join('');
    同步滚动();
  }

  function 重绘高亮() {
    if (!window.爻语法) return;
    高亮码.innerHTML = 爻语法.高亮(代码框.value, 谱);
    同步滚动();
  }

  function 同步滚动() {
    var 上 = 代码框.scrollTop;
    var 左 = 代码框.scrollLeft;
    高亮层.scrollTop = 上;
    高亮层.scrollLeft = 左;
    行号栏.scrollTop = 上;
  }

  function 排队重绘() {
    if (渲染排队) return;
    渲染排队 = true;
    var 走 = function () {
      渲染排队 = false;
      重绘高亮();
      重绘行号();
      更新统计();
    };
    if (window.requestAnimationFrame) requestAnimationFrame(走);
    else setTimeout(走, 16);
  }

  function 更新统计() {
    var 文 = 代码框.value;
    var 位 = 代码框.selectionStart || 0;
    字数量.textContent = 文.replace(/\n/g, '').length + ' 字';
    行号位.textContent = '第 ' + 当前行号(文, 位) + ' 行 第 ' +
      (位 - 行首偏移(文, 当前行号(文, 位)) + 1) + ' 列';
  }

  function 更新光行() {
    var 文 = 代码框.value;
    var 光行 = 当前行号(文, 代码框.selectionStart);
    var 子们 = 行号栏.children;
    for (var i = 0; i < 子们.length; i++) {
      var 应 = (i + 1) === 光行;
      if (应 !== 子们[i].classList.contains('当前')) 子们[i].classList.toggle('当前', 应);
    }
    更新统计();
  }

  function 设代码(文, 是否保存) {
    代码框.value = 文 == null ? '' : String(文);
    排队重绘();
    if (是否保存 !== false) 保存码();
  }

  var 存码定时 = null;
  function 保存码() {
    if (存码定时) clearTimeout(存码定时);
    存码定时 = setTimeout(function () {
      存码定时 = null;
      try { localStorage.setItem(存码键, 代码框.value); } catch (e) { /* 隐私模式忽略 */ }
    }, 240);
  }

  function 读码() {
    try { return localStorage.getItem(存码键); } catch (e) { return null; }
  }

  /* ── 编辑器事件 ───────────────────────────────────────── */
  代码框.addEventListener('input', function () {
    排队重绘();
    保存码();
    // 手动改过代码后，下拉不再声称「等于某个示例」
    示例选择.value = '';
  });

  代码框.addEventListener('scroll', 同步滚动, { passive: true });

  // 点击行号栏跳到该行（行号栏本身不可获得焦点）
  行号栏.addEventListener('click', function (事) {
    var 块 = 事.target.closest('.行号');
    if (!块) return;
    跳到(Number(块.textContent) || 1, 1);
  });

  ['click', 'keyup', 'select', 'focus'].forEach(function (名) {
    代码框.addEventListener(名, 更新光行);
  });

  document.addEventListener('selectionchange', function () {
    if (document.activeElement === 代码框) 更新光行();
  });

  代码框.addEventListener('keydown', function (事) {
    var 改键 = 事.ctrlKey || 事.metaKey;

    if (改键 && (事.key === 'Enter' || 事.keyCode === 13)) {
      事.preventDefault();
      跑();
      return;
    }

    if (事.key === 'Tab' && !改键 && !事.altKey) {
      事.preventDefault();
      var 起 = 代码框.selectionStart;
      var 止 = 代码框.selectionEnd;
      var 文 = 代码框.value;

      if (起 === 止 && !事.shiftKey) {
        插入文本('  ');
        return;
      }

      // 多行缩进 / 反缩进
      var 选区起 = 文.lastIndexOf('\n', 起 - 1) + 1;
      var 选区止 = 文.indexOf('\n', 止);
      if (选区止 < 0) 选区止 = 文.length;
      var 块 = 文.slice(选区起, 选区止);
      var 行们 = 块.split('\n');
      var 新行们 = 行们.map(function (行) {
        if (事.shiftKey) return 行.replace(/^ {1,2}/, '');
        return '  ' + 行;
      });
      var 新块 = 新行们.join('\n');
      代码框.setRangeText(新块, 选区起, 选区止, 'select');
      排队重绘();
      保存码();
      return;
    }

    // Ctrl+Enter 在部分输入法下 key 为 'Enter'，已处理；此处兜底 Ctrl+S 不刷新
    if (改键 && (事.key === 's' || 事.key === 'S')) {
      事.preventDefault();
      保存码();
    }
  });

  function 插入文本(文) {
    var 起 = 代码框.selectionStart;
    var 止 = 代码框.selectionEnd;
    // execCommand 保留撤销栈；失败则退回 setRangeText
    var 成 = false;
    try { 成 = document.execCommand('insertText', false, 文); } catch (e) { 成 = false; }
    if (!成) {
      代码框.setRangeText(文, 起, 止, 'end');
      排队重绘();
      保存码();
    } else {
      排队重绘();
      保存码();
    }
  }

  /* 跳到指定行/列：选中该行并把视口滚到中间。 */
  function 跳到(行, 列) {
    var 文 = 代码框.value;
    var 总行 = 行数(文);
    var 行号 = Math.min(Math.max(1, 行 | 0 || 1), 总行);
    var 列号 = Math.max(1, 列 | 0 || 1);
    var 起 = 行首偏移(文, 行号);
    var 行尾 = 文.indexOf('\n', 起);
    if (行尾 < 0) 行尾 = 文.length;
    var 位 = Math.min(起 + 列号 - 1, 行尾);

    代码框.focus();
    代码框.setSelectionRange(位, 位);
    var 目标上 = 编上内边 + (行号 - 1) * 行高;
    var 视高 = 代码框.clientHeight;
    if (目标上 < 代码框.scrollTop || 目标上 + 行高 > 代码框.scrollTop + 视高) {
      代码框.scrollTop = Math.max(0, 目标上 - 视高 / 2);
    }
    if (代码框.scrollLeft) 代码框.scrollLeft = 0;
    同步滚动();
    更新光行();
  }

  /* 从「第 N 行 第 M 列」文本里解析定位（后端已给 行/列，这里兜底）。 */
  function 解析定位(文) {
    var 配 = /第\s*(\d+)\s*行(?:\s*第\s*(\d+)\s*列)?/.exec(文 || '');
    if (!配) return null;
    return { 行: parseInt(配[1], 10), 列: 配[2] ? parseInt(配[2], 10) : 1 };
  }

  /* ── 运行 ─────────────────────────────────────────────── */
  function 置运行态(开) {
    运行中 = 开;
    运行按钮.disabled = 开;
    运行按钮.classList.toggle('运行中', 开);
    运行按钮.setAttribute('aria-busy', 开 ? 'true' : 'false');
    var 文字 = 运行按钮.querySelector('.按钮文字');
    if (文字) 文字.textContent = 开 ? '运行中…' : '运行';
    if (开) {
      运行状态.textContent = '运行中';
      运行状态.className = '状态徽 运行';
      状态提示.textContent = '正在执行，最长 5 秒…';
    }
  }

  function 清结果() {
    错误块.hidden = true;
    调用栈区.hidden = true;
    栈列.innerHTML = '';
    设置提示('');
  }

  function 显示输出(文) {
    // 后端子进程在 Windows 上可能回 \r\n，显示前统一为 \n（复制结果也更干净）
    if (typeof 文 === 'string') 文 = 文.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    if (文 && 文.length) {
      标准输出.textContent = 文;
    } else {
      标准输出.innerHTML = '<span class="占位">（暂无输出）</span>';
    }
    标准输出.scrollTop = 0;
  }

  function 取栈帧行(帧文) {
    var 配 = /[:：](\d+)\s*\)?/.exec(帧文 || '');
    return 配 ? parseInt(配[1], 10) : 0;
  }

  function 显示错误(错, 耗, 出) {
    var 类 = (错 && 错.类) || '错';
    错误类.textContent = 类;

    var 错文 = String((错 && 错.文) || '执行失败（后端未给出说明）');
    // 真实后端会把调用栈附在「文」里（换行 + 两空格缩进）。
    // 首行留在红色错误栏，其余缩进行收进下方「调用栈」面板，避免重复且更好读。
    var 文行们 = 错文.split(/\r?\n/);
    var 首行 = 文行们.shift() || 错文;
    错误文.textContent = 首行;

    var 定位 = null;
    if (错 && typeof 错.行 === 'number' && 错.行 > 0) {
      定位 = { 行: 错.行, 列: (typeof 错.列 === 'number' && 错.列 > 0 ? 错.列 : 1) };
    } else {
      定位 = 解析定位(首行);
    }
    // 有可定位的行号时显示「跳到出错位置」按钮；否则隐藏（错误正文始终可见）。
    if (定位 && 定位.行 > 0 && 定位.行 <= 行数(代码框.value)) {
      错误定位.hidden = false;
      错误跳转文.textContent = '跳到第 ' + 定位.行 + ' 行' +
        (定位.列 ? ' 第 ' + 定位.列 + ' 列' : '');
      错误定位.title = '点击跳到第 ' + 定位.行 + ' 行' + (定位.列 ? ' 第 ' + 定位.列 + ' 列' : '');
      错误定位.onclick = function () { 跳到(定位.行, 定位.列); };
    } else {
      错误定位.hidden = true;
      错误定位.onclick = null;
    }

    var 栈 = [];
    var 源栈 = (错 && 错.栈) || [];
    for (var s = 0; s < 源栈.length; s++) 栈.push(String(源栈[s]));
    for (var t = 0; t < 文行们.length; t++) {
      var 余 = 文行们[t].trim();
      if (余 && 栈.indexOf(余) < 0) 栈.push(余);
    }

    if (栈.length) {
      栈列.innerHTML = '';
      for (var i = 0; i < 栈.length; i++) {
        var 原文 = 栈[i];
        var 条 = document.createElement('li');
        // 栈帧形如「在 匠 算账(1 参)(片段.yao:1) 调用处」，取其中的 :N 作为行号
        var 帧行 = 取栈帧行(原文);
        if (帧行) {
          var 链接 = document.createElement('button');
          链接.type = 'button';
          链接.className = '栈跳';
          链接.textContent = 原文;
          链接.title = '跳到第 ' + 帧行 + ' 行';
          链接.setAttribute('data-行', String(帧行));
          链接.addEventListener('click', function (事) {
            跳到(Number(事.currentTarget.getAttribute('data-行')), 1);
          });
          条.appendChild(链接);
        } else {
          条.textContent = 原文;
        }
        栈列.appendChild(条);
      }
      调用栈区.hidden = false;
    } else {
      调用栈区.hidden = true;
      栈列.innerHTML = '';
    }

    错误块.hidden = false;

    if (类 === '时误') {
      状态提示.textContent = '执行超时：代码运行超过 5 秒已被终止（' + 耗 + ' 毫秒）';
    } else {
      状态提示.textContent = '执行失败 · ' + 类 + (定位 && 定位.行 ? ' · 第 ' + 定位.行 + ' 行' : '');
    }
    显示输出(出);
  }

  function 运行失败提示(文) {
    运行状态.textContent = '未运行';
    运行状态.className = '状态徽 失败';
    状态提示.textContent = '后端不可达';
    设置提示(文, true);
    标准输出.innerHTML = '<span class="占位">（没有拿到执行结果）</span>';
    耗时位.textContent = '';
    错误块.hidden = true;
    调用栈区.hidden = true;
  }

  function 跑() {
    if (运行中) return;
    清结果();
    置运行态(true);
    显示输出('');
    错误块.hidden = true;
    耗时位.textContent = '';
    if (当前页() !== '输出') 切页('输出');
    var 起 = 秒表();
    var 控 = window.AbortController ? new AbortController() : null;
    var 计时 = 控 ? setTimeout(function () { 控.abort(); }, 12000) : null;

    fetch('/api/跑', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 码: 代码框.value, 参: [] }),
      signal: 控 ? 控.signal : undefined
    }).then(function (应) {
      if (!应.ok) throw new Error('HTTP ' + 应.status);
      return 应.json();
    }).then(function (果) {
      if (计时) clearTimeout(计时);
      置运行态(false);
      var 耗 = (果 && typeof 果.耗 === 'number') ? 果.耗 : Math.round(秒表() - 起);
      耗时位.textContent = '耗时 ' + 耗 + ' 毫秒';
      var 出 = (果 && typeof 果.出 === 'string') ? 果.出 : '';
      if (果 && 果.成) {
        运行状态.textContent = '成功';
        运行状态.className = '状态徽 成功';
        状态提示.textContent = '执行成功 · 耗时 ' + 耗 + ' 毫秒';
        显示输出(出);
      } else {
        运行状态.textContent = 果 && 果.错 && 果.错.类 === '时误' ? '超时' : '失败';
        运行状态.className = '状态徽 失败';
        显示错误((果 && 果.错) || { 类: '内误', 文: '执行失败（后端未给出错误说明）', 栈: [] }, 耗, 出);
      }
    }).catch(function (误) {
      if (计时) clearTimeout(计时);
      置运行态(false);
      if (误 && 误.name === 'AbortError') {
        运行失败提示('请求后端超时：12 秒内没有收到应答。请确认服务仍在运行，或简化代码后重试。');
      } else {
        运行失败提示('无法连接后端（' + 中文错误(误, '网络错误') +
          '）。请确认已在项目目录执行「python -m yao 站」，并保持本页地址与端口一致。');
      }
    });
  }

  运行按钮.addEventListener('click', 跑);

  清空按钮.addEventListener('click', function () {
    if (代码框.value && !window.confirm('确定清空编辑器中的代码吗？（本机另存的最后代码也会被覆盖）')) return;
    设代码('');
    示例选择.value = '';
    重置结果();
    代码框.focus();
  });

  function 重置结果() {
    清结果();
    运行状态.textContent = '就绪';
    运行状态.className = '状态徽';
    状态提示.textContent = '按 Ctrl+Enter 运行当前代码';
    耗时位.textContent = '';
    显示输出('');
  }

  /* ── 健康检查 ─────────────────────────────────────────── */
  function 查健康() {
    var 控 = window.AbortController ? new AbortController() : null;
    var 计时 = 控 ? setTimeout(function () { 控.abort(); }, 3000) : null;
    fetch('/api/健康', { signal: 控 ? 控.signal : undefined, cache: 'no-store' })
      .then(function (应) { if (!应.ok) throw new Error('HTTP ' + 应.status); return 应.json(); })
      .then(function (数) {
        if (计时) clearTimeout(计时);
        if (数 && 数.行) {
          设置后端(true, '后端已连接');
          if (数.版) 版本号.textContent = 数.版;
        } else {
          设置后端(false, '后端状态异常');
        }
      })
      .catch(function () {
        if (计时) clearTimeout(计时);
        设置后端(false, '后端未连接');
        设置提示('无法连接爻语后端。请在项目目录执行「python -m yao 站」后刷新本页；' +
          '若已用其他端口启动，请按该端口访问。', true);
      });
  }

  /* ── 示例 ─────────────────────────────────────────────── */
  function 置示例选项(列表) {
    示例选择.innerHTML = '';
    if (!列表.length) {
      var 空 = document.createElement('option');
      空.value = '';
      空.textContent = '（暂无示例）';
      示例选择.appendChild(空);
      示例选择.disabled = true;
      return;
    }
    示例选择.appendChild(建选项('', '（自选代码）'));
    for (var i = 0; i < 列表.length; i++) {
      var 项 = 列表[i];
      示例选择.appendChild(建选项(项.名, 项.名));
    }
    示例选择.disabled = false;
  }

  function 建选项(值, 文) {
    var 选 = document.createElement('option');
    选.value = 值;
    选.textContent = 文;
    return 选;
  }

  function 载例(名) {
    for (var i = 0; i < 例子.length; i++) {
      if (例子[i].名 === 名) {
        设代码(例子[i].码);
        置运行态(false);
        重置结果();
        示例选择.value = 名;
        代码框.focus();
        return true;
      }
    }
    return false;
  }

  示例选择.addEventListener('change', function () {
    var 名 = 示例选择.value;
    if (!名) return;
    载例(名);
  });

  /* 载入默认示例：优先「你好」，没有就用第一个。 */
  function 载默认例() {
    if (载例(示例默认)) return;
    if (例子.length) 载例(例子[0].名);
  }

  function 取示例() {
    fetch('/api/例', { cache: 'no-store' })
      .then(function (应) { if (!应.ok) throw new Error('HTTP ' + 应.status); return 应.json(); })
      .then(function (数) {
        例子 = (数 && Array.isArray(数.例子)) ? 数.例子 : [];
        置示例选项(例子);
        var 存档 = 读码();
        if (存档 != null && 存档 !== '') {
          // 恢复上次代码；若与某个示例完全相同，则下拉显示该示例
          设代码(存档, false);
          重置结果();
          var 命中 = '';
          for (var i = 0; i < 例子.length; i++) {
            if (例子[i].码 === 存档) { 命中 = 例子[i].名; break; }
          }
          示例选择.value = 命中;   // 命中为空即「（自选代码）」
        } else if (例子.length) {
          载默认例();
        } else {
          设代码('', false);
          重置结果();
        }
      })
      .catch(function (误) {
        示例选择.innerHTML = '';
        示例选择.appendChild(建选项('', '（示例加载失败）'));
        示例选择.disabled = true;
        if (!读码()) 设代码('注 无法连接后端，示例未能加载。\n注 请先执行「python -m yao 站」。\n显("你好")\n', false);
        设置提示('示例列表加载失败（' + 中文错误(误, '网络错误') +
          '）。请确认爻语后端已启动。', true);
      });
  }

  /* ── 速查 ─────────────────────────────────────────────── */
  var 分组 = [
    { 键: '关键字', 名: '关键字', 类: '' },
    { 键: '内置', 名: '内置函数', 类: '内置' },
    { 键: '运算', 名: '运算符', 类: '运算' }
  ];

  function 渲染速查(过滤) {
    if (!谱) {
      速查提示.hidden = false;
      速查提示.textContent = '正在加载语言谱…';
      return;
    }
    var 查 = (过滤 || '').trim().toLowerCase();
    var 片 = [];
    var 总 = 0;

    for (var g = 0; g < 分组.length; g++) {
      var 组 = 分组[g];
      var 源 = Array.isArray(谱[组.键]) ? 谱[组.键] : [];
      var 命中 = [];
      for (var i = 0; i < 源.length; i++) {
        var 项 = 源[i] || {};
        var 词 = String(项.词 == null ? '' : 项.词);
        var 义 = String(项.义 == null ? '' : 项.义);
        if (!查 || 词.toLowerCase().indexOf(查) >= 0 || 义.toLowerCase().indexOf(查) >= 0) {
          命中.push({ 词: 词, 义: 义 });
        }
      }
      总 += 命中.length;
      if (!命中.length) continue;
      片.push(
        '<section class="速查组" data-组="' + 组.名 + '">' +
          '<div class="速查组头"><h3>' + 组.名 + '</h3>' +
            '<span class="计数">' + 命中.length + ' 条</span></div>' +
          '<div class="速查表">' +
            命中.map(function (项) {
              return '<div class="速查词 ' + 组.类 + '">' + 爻语法.转义(项.词) + '</div>' +
                     '<div class="速查义">' + 爻语法.转义(项.义) + '</div>';
            }).join('') +
          '</div>' +
        '</section>'
      );
    }

    if (!总) {
      速查内容.innerHTML = '<p class="速查空">没有匹配「' + 爻语法.转义(查) +
        '」的关键字、内置函数或运算符。</p>';
    } else {
      速查内容.innerHTML = 片.join('');
    }
    速查内容.setAttribute('data-总条数', String(总));
  }

  过滤输入.addEventListener('input', function () {
    渲染速查(过滤输入.value);
  });

  过滤输入.addEventListener('keydown', function (事) {
    if (事.key === 'Escape') {
      过滤输入.value = '';
      渲染速查('');
    }
  });

  function 取谱() {
    fetch('/api/谱', { cache: 'no-store' })
      .then(function (应) { if (!应.ok) throw new Error('HTTP ' + 应.status); return 应.json(); })
      .then(function (数) {
        谱 = 数 || { 关键字: [], 内置: [], 运算: [] };
        渲染速查('');
        排队重绘();
        速查提示.hidden = true;
      })
      .catch(function () {
        谱 = null;
        速查提示.hidden = false;
        速查提示.textContent = '语言谱加载失败：无法连接后端。后端启动后刷新本页即可。';
      });
  }

  /* ── 标签页 ───────────────────────────────────────────── */
  function 当前页() {
    for (var i = 0; i < 标签们.length; i++) {
      if (标签们[i].classList.contains('活动')) return 标签们[i].getAttribute('data-页');
    }
    return '输出';
  }

  function 切页(名) {
    for (var i = 0; i < 标签们.length; i++) {
      var 标 = 标签们[i];
      var 活 = 标.getAttribute('data-页') === 名;
      标.classList.toggle('活动', 活);
      标.setAttribute('aria-selected', 活 ? 'true' : 'false');
    }
    for (var 键 in 页们) {
      if (!Object.prototype.hasOwnProperty.call(页们, 键)) continue;
      页们[键].hidden = 键 !== 名;
      页们[键].classList.toggle('活动', 键 === 名);
    }
    if (名 === '速查') {
      渲染速查(过滤输入.value);
      setTimeout(function () { 过滤输入.focus(); }, 30);
    }
  }

  标签们.forEach(function (标) {
    标.addEventListener('click', function () { 切页(标.getAttribute('data-页')); });
    标.addEventListener('keydown', function (事) {
      if (事.key === 'ArrowRight' || 事.key === 'ArrowLeft') {
        事.preventDefault();
        var 下 = 事.key === 'ArrowRight' ? 1 : -1;
        var 位 = 标签们.indexOf(标);
        var 新 = 标签们[(位 + 下 + 标签们.length) % 标签们.length];
        切页(新.getAttribute('data-页'));
        新.focus();
      }
    });
  });

  /* ── 窗口尺寸变化 ─────────────────────────────────────── */
  var 缩时 = null;
  window.addEventListener('resize', function () {
    if (缩时) clearTimeout(缩时);
    缩时 = setTimeout(function () {
      缩时 = null;
      取度量();
      重绘行号();
      同步滚动();
    }, 120);
  });

  /* ── 启动 ─────────────────────────────────────────────── */
  function 启动() {
    取度量();
    重绘高亮();
    重绘行号();
    更新统计();
    查健康();
    取谱();
    取示例();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', 启动);
  } else {
    启动();
  }

  // 暴露少量调试接口（便于自动化验证，不影响用户）
  window.爻IDE = {
    跑: 跑,
    取谱: function () { return 谱; },
    取例子: function () { return 例子; },
    取码: function () { return 代码框.value; },
    设码: 设代码,
    切页: 切页,
    跳到: 跳到
  };
}());
