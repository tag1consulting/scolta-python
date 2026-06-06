<?php
declare(strict_types=1);
require __DIR__ . '/../../scolta-php/vendor/autoload.php';

use Tag1\Scolta\Html\HtmlCleaner;
use Tag1\Scolta\Html\PagefindHtmlBuilder;

$phpFixtures = __DIR__ . '/../../scolta-php/tests/fixtures/recipes';

$out = ['cleaner_fixtures' => [], 'cleaner_units' => [], 'builder_cases' => []];

// 1. Recipe fixtures: clean with no title and with the title extracted from <title>.
foreach (glob($phpFixtures . '/*.html') as $path) {
    $name = basename($path);
    $html = file_get_contents($path);
    preg_match('/<title>(.*?)<\/title>/s', $html, $m);
    $title = $m[1] ?? '';
    $out['cleaner_fixtures'][$name] = [
        'title' => $title,
        'clean_no_title' => HtmlCleaner::clean($html),
        'clean_with_title' => HtmlCleaner::clean($html, $title),
    ];
}

// 2. Unit-test + edge-case raw inputs -> cleaned output (exact match).
$units = [
    'basic' => ['<p>Hello <strong>world</strong></p>', ''],
    'script' => ['<p>Content</p><script>alert("xss")</script><p>More</p>', ''],
    'multiline_script' => ["<p>Before</p>\n<script type=\"text/javascript\">\n  var x = 1;\n  console.log(x);\n</script>\n<p>After</p>", ''],
    'multiline_style' => ["<p>Before</p>\n<style>\n  body { color: red; }\n  h1 { font-size: 2em; }\n</style>\n<p>After</p>", ''],
    'comments' => ['<p>Visible</p><!-- This is a comment --><p>Also visible</p>', ''],
    'main_content' => ['<nav>Navigation</nav><div id="main-content"><p>Important content here</p></div><footer>Footer stuff</footer>', ''],
    'main_case_insensitive' => ['<div>Outside</div><DIV ID="main-content"><p>Inside main</p></DIV><div>Also outside</div>', ''],
    'footer_class' => ['<p>Content</p><div class="site-footer"><p>Footer content</p></div>', ''],
    'footer_id' => ['<p>Content</p><div id="page-footer"><p>Footer content</p></div>', ''],
    'malformed' => ['<p>Unclosed paragraph<div>Mixed <b>nesting</div></b>', ''],
    'empty' => ['', ''],
    'nav' => ['<nav><ul><li>Home</li><li>About</li></ul></nav><main><p>Page content here</p></main>', ''],
    'entities_amp' => ['<p>Tom &amp; Jerry &lt;tag&gt; &quot;q&quot; &#39;a&#39;</p>', ''],
    'nbsp' => ['<p>a&nbsp;&nbsp;b   c</p>', ''],
    'nested_main' => ['<div id="main-content">outer <div>inner content</div> tail</div>after', ''],
    'lt_space_literal' => ['<p>2 &lt; 3 and a < b here</p>', ''],
    'title_strip' => ['<h1>My Title</h1><p>The body begins here with content.</p>', 'My Title'],
    'title_not_at_start' => ['<p>Some intro text that is fairly long so the title appears past offset fifty chars My Title</p>', 'My Title'],
    'region_footer' => ['<p>Keep</p><div class="region-footer"><p>drop this footer</p></div>', ''],
    'unicode_diacritics' => ['<p>Café résumé naïve Zürich jalapeño</p>', ''],
];
foreach ($units as $key => [$html, $title]) {
    $out['cleaner_units'][$key] = [
        'input' => $html,
        'title' => $title,
        'expected' => HtmlCleaner::clean($html, $title),
    ];
}

// 3. PagefindHtmlBuilder byte-exact cases.
$builderCases = [
    ['id' => 'doc-1', 'title' => 'Test Title', 'body' => 'Body text here', 'url' => 'https://example.com/page', 'date' => '2024-06-15', 'siteName' => 'My Site'],
    ['id' => 'doc-2', 'title' => "Tom & Jerry's <Adventure>", 'body' => 'Content with "quotes" & <tags>', 'url' => 'https://example.com/page?a=1&b=2', 'date' => '2024-01-01', 'siteName' => 'Site "One"'],
    ['id' => 'doc-3', 'title' => 'No Site', 'body' => 'Body content', 'url' => 'https://example.com', 'date' => '2024-01-01', 'siteName' => ''],
    ['id' => 'doc-4', 'title' => 'English', 'body' => 'Body', 'url' => 'https://example.com'],
    ['id' => 'doc-5', 'title' => 'Español', 'body' => 'Contenido en español', 'url' => 'https://example.com/es', 'date' => '2024-06-15', 'siteName' => 'Mi Sitio', 'language' => 'es'],
    ['id' => 'doc-7', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'filters' => ['base_topic' => 'Cardiology', 'region' => 'Europe']],
    ['id' => 'doc-8', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'filters' => ['category' => 'Rock & Roll <genre>']],
    ['id' => 'doc-multi', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'filters' => ['topics' => ['Science', 'History']]],
    ['id' => 'doc-10', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'metadata' => ['price' => '29.99', 'rating' => '4.5']],
    ['id' => 'doc-13', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'sortable' => ['price' => '29.99', 'rating' => '4.5']],
    ['id' => 'doc-16', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'metadata' => ['published' => '2024-06-15'], 'sortable' => ['price' => '9.99']],
    ['id' => 'doc-17', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'date' => '2026-05-15'],
    ['id' => 'doc-18', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'date' => '2026-05-15', 'sortable' => ['date' => '2026-01-01']],
    ['id' => 'doc-19', 'title' => 'Test', 'body' => 'Body', 'url' => 'https://example.com', 'date' => ''],
];
foreach ($builderCases as $c) {
    $params = [
        'id' => $c['id'], 'title' => $c['title'], 'body' => $c['body'], 'url' => $c['url'],
        'date' => $c['date'] ?? '', 'siteName' => $c['siteName'] ?? '', 'language' => $c['language'] ?? 'en',
        'filters' => $c['filters'] ?? [], 'metadata' => $c['metadata'] ?? [], 'sortable' => $c['sortable'] ?? [],
    ];
    $out['builder_cases'][] = [
        'params' => $params,
        'expected' => PagefindHtmlBuilder::build(
            $params['id'], $params['title'], $params['body'], $params['url'],
            $params['date'], $params['siteName'], $params['language'],
            $params['filters'], $params['metadata'], $params['sortable']
        ),
    ];
}

file_put_contents(
    __DIR__ . '/../tests/fixtures/html_parity.json',
    json_encode($out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
);
echo "wrote golden: fixtures=" . count($out['cleaner_fixtures']) . " units=" . count($out['cleaner_units']) . " builders=" . count($out['builder_cases']) . "\n";
