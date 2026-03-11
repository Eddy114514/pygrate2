#ifndef Py_PYGRATE_WARNING_UTILS_H
#define Py_PYGRATE_WARNING_UTILS_H

#include <string.h>

#include "frameobject.h"
#include "opcode.h"

typedef struct {
    const char *filename;
    const char *funcname;
    const char *call_opname;
    const char *consumer_opname;
    const char *consumer_kind;
    int lineno;
    int call_offset;
    int consumer_offset;
} PygrateWarningContext;

static const char *
pygrate_call_op_name(int opcode)
{
    switch (opcode) {
    case CALL_FUNCTION:
        return "CALL_FUNCTION";
    case CALL_FUNCTION_VAR:
        return "CALL_FUNCTION_VAR";
    case CALL_FUNCTION_KW:
        return "CALL_FUNCTION_KW";
    case CALL_FUNCTION_VAR_KW:
        return "CALL_FUNCTION_VAR_KW";
    default:
        return NULL;
    }
}

static const char *
pygrate_consumer_op_name(int opcode)
{
    switch (opcode) {
    case CALL_FUNCTION:
        return "CALL_FUNCTION";
    case CALL_FUNCTION_VAR:
        return "CALL_FUNCTION_VAR";
    case CALL_FUNCTION_KW:
        return "CALL_FUNCTION_KW";
    case CALL_FUNCTION_VAR_KW:
        return "CALL_FUNCTION_VAR_KW";
    case GET_ITER:
        return "GET_ITER";
    case BINARY_ADD:
        return "BINARY_ADD";
    case INPLACE_ADD:
        return "INPLACE_ADD";
    case BINARY_SUBSCR:
        return "BINARY_SUBSCR";
    case STORE_SUBSCR:
        return "STORE_SUBSCR";
    case COMPARE_OP:
        return "COMPARE_OP";
    case RETURN_VALUE:
        return "RETURN_VALUE";
    case STORE_FAST:
        return "STORE_FAST";
    case STORE_NAME:
        return "STORE_NAME";
    case STORE_ATTR:
        return "STORE_ATTR";
    case STORE_GLOBAL:
        return "STORE_GLOBAL";
    default:
        return NULL;
    }
}

static const char *
pygrate_consumer_kind_name(const char *opname)
{
    if (opname == NULL)
        return NULL;
    if (strcmp(opname, "GET_ITER") == 0)
        return "iteration";
    if (strncmp(opname, "CALL_FUNCTION", 13) == 0)
        return "call";
    if (strcmp(opname, "BINARY_ADD") == 0 || strcmp(opname, "INPLACE_ADD") == 0)
        return "binary_add";
    if (strcmp(opname, "BINARY_SUBSCR") == 0 || strcmp(opname, "STORE_SUBSCR") == 0)
        return "subscript";
    if (strcmp(opname, "COMPARE_OP") == 0)
        return "compare";
    if (strcmp(opname, "RETURN_VALUE") == 0)
        return "return";
    if (strncmp(opname, "STORE_", 6) == 0)
        return "store";
    return "other";
}

static int
pygrate_code_bytes(PyCodeObject *code, const unsigned char **bc, Py_ssize_t *n)
{
#if PY_MAJOR_VERSION >= 3
    if (!PyBytes_Check(code->co_code))
        return 0;
    *bc = (const unsigned char *)PyBytes_AS_STRING(code->co_code);
    *n = PyBytes_GET_SIZE(code->co_code);
#else
    if (!PyString_Check(code->co_code))
        return 0;
    *bc = (const unsigned char *)PyString_AS_STRING(code->co_code);
    *n = PyString_GET_SIZE(code->co_code);
#endif
    return 1;
}

static int
pygrate_next_instruction_offset(const unsigned char *bc, Py_ssize_t n, int offset)
{
    int next;
    if (bc == NULL || offset < 0 || (Py_ssize_t)offset >= n)
        return -1;
    next = offset + 1;
    if (bc[offset] >= HAVE_ARGUMENT)
        next += 2;
    if ((Py_ssize_t)next > n)
        return -1;
    return next;
}

static void
pygrate_find_consumer(PyCodeObject *code, int call_offset,
                      const char **consumer_opname,
                      const char **consumer_kind,
                      int *consumer_offset)
{
    const unsigned char *bc;
    Py_ssize_t n;
    int cursor;

    *consumer_opname = NULL;
    *consumer_kind = NULL;
    *consumer_offset = -1;

    if (!pygrate_code_bytes(code, &bc, &n))
        return;

    cursor = pygrate_next_instruction_offset(bc, n, call_offset);
    while (cursor >= 0 && (Py_ssize_t)cursor < n) {
        int op = bc[cursor];
        const char *name = pygrate_consumer_op_name(op);
        if (name != NULL) {
            *consumer_opname = name;
            *consumer_kind = pygrate_consumer_kind_name(name);
            *consumer_offset = cursor;
            return;
        }
        cursor = pygrate_next_instruction_offset(bc, n, cursor);
    }
}

static int
pygrate_capture_warning_context(PygrateWarningContext *ctx)
{
    PyFrameObject *cur;
    PyFrameObject *caller;
    const unsigned char *bc;
    Py_ssize_t n;

    if (ctx == NULL)
        return 0;

    ctx->filename = "<unknown>";
    ctx->funcname = "<unknown>";
    ctx->call_opname = NULL;
    ctx->consumer_opname = NULL;
    ctx->consumer_kind = NULL;
    ctx->lineno = 0;
    ctx->call_offset = -1;
    ctx->consumer_offset = -1;

    cur = PyEval_GetFrame();
    caller = (cur && cur->f_back) ? cur->f_back : cur;
    if (caller == NULL || caller->f_code == NULL)
        return 0;

#if PY_MAJOR_VERSION >= 3
    ctx->filename = PyUnicode_AsUTF8(caller->f_code->co_filename);
    ctx->funcname = PyUnicode_AsUTF8(caller->f_code->co_name);
#else
    ctx->filename = PyString_AsString(caller->f_code->co_filename);
    ctx->funcname = PyString_AsString(caller->f_code->co_name);
#endif
    if (ctx->filename == NULL)
        ctx->filename = "<non-utf8 filename>";
    if (ctx->funcname == NULL)
        ctx->funcname = "<non-utf8 func>";

    ctx->lineno = PyFrame_GetLineNumber(caller);
    ctx->call_offset = caller->f_lasti;

    if (pygrate_code_bytes(caller->f_code, &bc, &n) &&
            ctx->call_offset >= 0 && (Py_ssize_t)ctx->call_offset < n) {
        ctx->call_opname = pygrate_call_op_name((int)bc[ctx->call_offset]);
        pygrate_find_consumer(caller->f_code, ctx->call_offset,
                              &ctx->consumer_opname,
                              &ctx->consumer_kind,
                              &ctx->consumer_offset);
    }

    return 1;
}

static void
pygrate_json_quote_or_null(char *buf, size_t size, const char *value)
{
    if (value == NULL || *value == '\0')
        PyOS_snprintf(buf, size, "null");
    else
        PyOS_snprintf(buf, size, "\"%s\"", value);
}

static const char *
pygrate_bool_json(int value)
{
    if (value < 0)
        return "null";
    return value ? "true" : "false";
}

static int
pygrate_warn_py3k_with_context(const char *base_msg,
                               const PygrateWarningContext *ctx,
                               const char *callee_kind,
                               const char *receiver_type,
                               int materialization_required,
                               int text_consumer,
                               const char *suggested_codec,
                               Py_ssize_t stacklevel)
{
    char callee_json[128];
    char receiver_json[128];
    char consumer_op_json[64];
    char consumer_kind_json[64];
    char codec_json[64];
    char meta[1024];
    char message[4096];
    const char *filename;
    const char *funcname;
    const char *call_opname;
    int lineno;
    int call_offset;

    filename = (ctx && ctx->filename) ? ctx->filename : "<unknown>";
    funcname = (ctx && ctx->funcname) ? ctx->funcname : "<unknown>";
    call_opname = ctx ? ctx->call_opname : NULL;
    lineno = ctx ? ctx->lineno : 0;
    call_offset = ctx ? ctx->call_offset : -1;

    pygrate_json_quote_or_null(callee_json, sizeof(callee_json), callee_kind);
    pygrate_json_quote_or_null(receiver_json, sizeof(receiver_json), receiver_type);
    pygrate_json_quote_or_null(consumer_op_json, sizeof(consumer_op_json),
                               ctx ? ctx->consumer_opname : NULL);
    pygrate_json_quote_or_null(consumer_kind_json, sizeof(consumer_kind_json),
                               ctx ? ctx->consumer_kind : NULL);
    pygrate_json_quote_or_null(codec_json, sizeof(codec_json), suggested_codec);

    PyOS_snprintf(
        meta,
        sizeof(meta),
        "{\"bytecode_offset\":%d,\"consumer_offset\":%d,"
        "\"consumer_op\":%s,\"consumer_kind\":%s,"
        "\"materialization_required\":%s,\"text_consumer\":%s,"
        "\"suggested_codec\":%s,\"receiver_type\":%s,"
        "\"callee_kind\":%s}",
        call_offset,
        ctx ? ctx->consumer_offset : -1,
        consumer_op_json,
        consumer_kind_json,
        pygrate_bool_json(materialization_required),
        pygrate_bool_json(text_consumer),
        codec_json,
        receiver_json,
        callee_json
    );

    if (call_opname != NULL) {
        PyOS_snprintf(
            message,
            sizeof(message),
            "%s (called from %s:%d in %s, bytecode=%s@%d)\n"
            "  [pygrate-meta] %s",
            base_msg,
            filename,
            lineno,
            funcname,
            call_opname,
            call_offset,
            meta
        );
    }
    else if (call_offset >= 0) {
        PyOS_snprintf(
            message,
            sizeof(message),
            "%s (called from %s:%d in %s, bytecode@%d)\n"
            "  [pygrate-meta] %s",
            base_msg,
            filename,
            lineno,
            funcname,
            call_offset,
            meta
        );
    }
    else {
        PyOS_snprintf(
            message,
            sizeof(message),
            "%s (called from %s:%d in %s)\n"
            "  [pygrate-meta] %s",
            base_msg,
            filename,
            lineno,
            funcname,
            meta
        );
    }

    return PyErr_WarnPy3k(message, stacklevel);
}

#endif
