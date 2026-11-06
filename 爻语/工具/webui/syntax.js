/* 爻语语法高亮器（自写分词器，零依赖、可离线）
 *
 * 设计约定：
 *   1. 关键字、内置函数、运算符词表全部由调用方从 /api/谱 取得后传入，
 *      前端不硬编码第二套词表，避免与解释器实现漂移。
 *   2. 只做「着色」，不做校验，任何输入都必须能安全输出（HTML 已转义）。
 *   3. 支持：注 行注释、注【 】（可嵌套）块注释、'字'/"字"、数字、
 *      反引号标识符、⇒ ▷ 【 】 运算符与标点。
 *
 * 用法：
 *   高亮(码字符串, 谱对象) -> HTML 字符串
 *   谱对象形如 {"关键字":[{"词","义"}], "内置":[...], "运算":[...]}，可为 null。
 */
(function (global) {
  'use strict';

  // 规格 3.1 中属于「字面量 / 逻辑」的关键字，单独用醒目颜色。
  // 这里只做配色微调，不承担「关键字全集」的职责（全集来自 /api/谱）。
  var 特殊字 = { '它': 1, '真': 1, '假': 1, '空': 1, '且': 1, '或': 1, '非': 1 };

  var 双字符号 = ['==', '!=', '<=', '>=', '=>', '|>'];
  var 强符号 = { '⇒': 1, '▷': 1 };
  var 块符号 = { '【': 1, '】': 1 };
  var 分隔符号 = { '；': 1, ';': 1, '，': 1, ',': 1 };
  var 算术符号 = '+-*/%^<>=!';
  var 标点符号 = '()[]{}.:';

  function 转义(文) {
    return String(文)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function 是汉字(码) {
    return 码 >= 0x4e00 && 码 <= 0x9fff;
  }

  function 是标识起(文, 位) {
    var 码 = 文.charCodeAt(位);
    if (是汉字(码)) return true;
    var 字 = 文.charAt(位);
    return (字 >= 'a' && 字 <= 'z') || (字 >= 'A' && 字 <= 'Z') || 字 === '_';
  }

  function 是标识续(文, 位) {
    var 字 = 文.charAt(位);
    if (字 >= '0' && 字 <= '9') return true;
    return 是标识起(文, 位);
  }

  function 是数字(文, 位) {
    var 字 = 文.charAt(位);
    return 字 >= '0' && 字 <= '9';
  }

  /* 把 /api/谱 的三组列表转成查表用的对象。 */
  function 造词表(谱) {
    var 表 = { 关键字: Object.create(null), 内置: Object.create(null) };
    if (!谱) return 表;
    var 组 = [
      { 源: 谱.关键字, 标: 表.关键字 },
      { 源: 谱.内置, 标: 表.内置 }
    ];
    for (var i = 0; i < 组.length; i++) {
      var 列表 = 组[i].源;
      if (!列表 || !列表.length) continue;
      for (var j = 0; j < 列表.length; j++) {
        var 项 = 列表[j];
        if (项 && 项.词) 组[i].标[项.词] = 项.义 || '';
      }
    }
    return 表;
  }

  function 高亮(码, 谱) {
    var 词表 = 造词表(谱);
    var 文 = 码 == null ? '' : String(码);
    var 长 = 文.length;
    var 片 = [];
    var 平 = '';
    var i = 0;

    function 冲平() {
      if (平) { 片.push(转义(平)); 平 = ''; }
    }
    function 推(类名, 内容) {
      冲平();
      片.push('<span class="' + 类名 + '">' + 转义(内容) + '</span>');
    }

    while (i < 长) {
      var 字 = 文.charAt(i);

      /* —— 注释 —— */
      if (字 === '注') {
        if (文.charAt(i + 1) === '【') {
          // 块注释，允许嵌套：注【 … 注【 … 】 … 】
          var 深 = 1;
          var j = i + 2;
          while (j < 长 && 深 > 0) {
            if (文.charAt(j) === '注' && 文.charAt(j + 1) === '【') { 深++; j += 2; }
            else if (文.charAt(j) === '】') { 深--; j += 1; }
            else j += 1;
          }
          推('tk-cmt', 文.slice(i, j));
          i = j;
          continue;
        }
        // 行注释：注 到行尾
        var 行尾 = 文.indexOf('\n', i);
        if (行尾 < 0) 行尾 = 长;
        推('tk-cmt', 文.slice(i, 行尾));
        i = 行尾;
        continue;
      }
      if (字 === '\n') { 平 += 字; i += 1; continue; }
      if (字 === ' ' || 字 === '\t' || 字 === '\r') { 平 += 字; i += 1; continue; }

      /* —— 字（字符串）—— */
      if (字 === '"' || 字 === "'") {
        var 引 = 字;
        var k = i + 1;
        while (k < 长) {
          var 当 = 文.charAt(k);
          if (当 === '\\' && k + 1 < 长) { k += 2; continue; }
          if (当 === 引) { k += 1; break; }
          if (当 === '\n') break; // 字面量不跨行
          k += 1;
        }
        推('tk-str', 文.slice(i, k));
        i = k;
        continue;
      }

      /* —— 反引号标识符 —— */
      if (字 === '`') {
        var 收 = 文.indexOf('`', i + 1);
        var 止 = 收 < 0 ? 长 : 收 + 1;
        推('tk-nam', 文.slice(i, 止));
        i = 止;
        continue;
      }

      /* —— 数字 —— */
      if (是数字(文, i)) {
        var n = i;
        while (n < 长 && 是数字(文, n)) n += 1;
        if (文.charAt(n) === '.' && 是数字(文, n + 1)) {
          n += 1;
          while (n < 长 && 是数字(文, n)) n += 1;
        }
        var 指 = 文.charAt(n);
        if (指 === 'e' || 指 === 'E') {
          var 后 = n + 1;
          if (文.charAt(后) === '+' || 文.charAt(后) === '-') 后 += 1;
          if (是数字(文, 后)) {
            n = 后;
            while (n < 长 && 是数字(文, n)) n += 1;
          }
        }
        推('tk-num', 文.slice(i, n));
        i = n;
        continue;
      }

      /* —— 标识符 / 关键字 / 内置 —— */
      if (是标识起(文, i)) {
        var m = i + 1;
        while (m < 长 && 是标识续(文, m)) m += 1;
        var 词 = 文.slice(i, m);
        if (词表.关键字[词]) {
          推(特殊字[词] ? 'tk-lit' : 'tk-kw', 词);
        } else if (词表.内置[词]) {
          推('tk-bi', 词);
        } else {
          平 += 词;
        }
        i = m;
        continue;
      }

      /* —— 双字符号 —— */
      var 双 = 文.substr(i, 2);
      var 命中 = false;
      for (var d = 0; d < 双字符号.length; d++) {
        if (双 === 双字符号[d]) { 推('tk-op', 双); i += 2; 命中 = true; break; }
      }
      if (命中) continue;

      /* —— 单字符号 —— */
      if (强符号[字]) { 推('tk-op', 字); i += 1; continue; }
      if (块符号[字]) { 推('tk-blk', 字); i += 1; continue; }
      if (分隔符号[字]) { 推('tk-punc', 字); i += 1; continue; }
      if (算术符号.indexOf(字) >= 0) { 推('tk-sym', 字); i += 1; continue; }
      if (标点符号.indexOf(字) >= 0) { 推('tk-punc', 字); i += 1; continue; }

      平 += 字;
      i += 1;
    }

    冲平();
    // 末尾补零宽空格：保证最后一行为空行时仍占一行高度，与 textarea 对齐。
    return 片.join('') + '\u200b';
  }

  global.爻语法 = {
    高亮: 高亮,
    转义: 转义
  };
}(typeof window !== 'undefined' ? window : this));
