/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 *  contributor license agreements.  The ASF licenses this file to You
 * under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.  For additional information regarding
 * copyright in this work, please see the NOTICE file in the top level
 * directory of this distribution.
 */

package org.apache.roller.weblogger.business;

import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.apache.roller.weblogger.config.WebloggerRuntimeConfig;
import org.apache.roller.weblogger.pojos.Weblog;
import org.apache.roller.weblogger.pojos.WeblogTheme;
import org.apache.roller.weblogger.util.URLUtilities;

/**
 * A URLStrategy used by the preview rendering system.
 */
public class PreviewURLStrategy extends MultiWeblogURLStrategy {

    private final String previewTheme;
    private static final String PREVIEW_URL_SEGMENT = "/roller-ui/authoring/preview/";

    public PreviewURLStrategy(String theme) {
        previewTheme = theme;
    }

    /**
     * Get root url for a given *preview* weblog.  
     * Optionally for a certain locale.
     */
    @Override
    public String getWeblogURL(Weblog weblog, String locale, boolean absolute) {
        if (weblog == null) {
            return null;
        }
        return buildPreviewURL(weblog, locale, absolute, Collections.emptyMap());
    }

    /**
     * Get url for a given *preview* weblog entry.  
     * Optionally for a certain locale.
     */
    @Override
    public String getWeblogEntryURL(Weblog weblog, String locale, String previewAnchor, boolean absolute) {
        if (weblog == null) {
            return null;
        }
        Map<String, String> params = new HashMap<>();
        if (previewTheme != null) {
            params.put("theme", URLUtilities.encode(previewTheme));
        }
        if (previewAnchor != null) {
            params.put("previewEntry", URLUtilities.encode(previewAnchor));
        }
        return buildPreviewURL(weblog, locale, absolute, params);
    }

    /**
     * Get url for a collection of entries on a given weblog.
     */
    @Override
    public String getWeblogCollectionURL(Weblog weblog, String locale, String category, String dateString, List<String> tags, int pageNum, boolean absolute) {
        if (weblog == null) {
            return null;
        }
        Map<String, String> params = new HashMap<>();
        StringBuilder pathinfo = new StringBuilder(URL_BUFFER_SIZE);
        buildPreviewPath(weblog, locale, absolute, pathinfo);
        buildCollectionPath(category, dateString, tags, pathinfo);
        buildPageParams(pageNum, params);
        buildThemeParam(previewTheme, params);
        return pathinfo.append(URLUtilities.getQueryString(params)).toString();
    }

    /**
     * Get url for a custom page on a given weblog.
     */
    @Override
    public String getWeblogPageURL(Weblog weblog, String locale, String pageLink, String entryAnchor, String category, String dateString, List<String> tags, int pageNum, boolean absolute) {
        if (weblog == null) {
            return null;
        }
        if (pageLink != null) {
            return buildPageURL(weblog, locale, pageLink, category, dateString, tags, pageNum, absolute);
        } else {
            return getWeblogCollectionURL(weblog, locale, category, dateString, tags, pageNum, absolute);
        }
    }

    /**
     * Get a url to a *preview* resource on a given weblog.
     */
    @Override
    public String getWeblogResourceURL(Weblog weblog, String filePath, boolean absolute) {
        if (weblog == null) {
            return null;
        }
        StringBuilder url = new StringBuilder(URL_BUFFER_SIZE);
        if (absolute) {
            url.append(WebloggerRuntimeConfig.getAbsoluteContextURL());
        } else {
            url.append(WebloggerRuntimeConfig.getRelativeContextURL());
        }
        url.append("/roller-ui/authoring/previewresource/").append(weblog.getHandle()).append('/');
        if (filePath.startsWith("/")) {
            url.append(filePath.substring(1));
        } else {
            url.append(filePath);
        }
        Map<String, String> params = Collections.emptyMap();
        if (previewTheme != null && !WeblogTheme.CUSTOM.equals(previewTheme)) {
            params = Map.of("theme", URLUtilities.encode(previewTheme));
        }
        return url.append(URLUtilities.getQueryString(params)).toString();
    }

    private String buildPreviewURL(Weblog weblog, String locale, boolean absolute, Map<String, String> params) {
        StringBuilder url = new StringBuilder(URL_BUFFER_SIZE);
        buildPreviewPath(weblog, locale, absolute, url);
        return url.append(URLUtilities.getQueryString(params)).toString();
    }

    private void buildPreviewPath(Weblog weblog, String locale, boolean absolute, StringBuilder url) {
        if (absolute) {
            url.append(WebloggerRuntimeConfig.getAbsoluteContextURL());
        } else {
            url.append(WebloggerRuntimeConfig.getRelativeContextURL());
        }
        url.append(PREVIEW_URL_SEGMENT).append(weblog.getHandle()).append('/');
        if (locale != null) {
            url.append(locale).append('/');
        }
    }

    private void buildCollectionPath(String category, String dateString, List<String> tags, StringBuilder pathinfo) {
        String cat;
        if ("root".equals(category)) {
            cat = null;
        } else {
            cat = category;
        }
        if (cat != null && dateString == null) {
            pathinfo.append("category/").append(URLUtilities.encodePath(cat));
        } else if (dateString != null && cat == null) {
            pathinfo.append("date/").append(dateString);
        } else if (tags != null && !tags.isEmpty()) {
            pathinfo.append("tags/").append(URLUtilities.getEncodedTagsString(tags));
        }
    }

    private void buildPageParams(int pageNum, Map<String, String> params) {
        if (pageNum > 0) {
            params.put("page", Integer.toString(pageNum));
        }
    }

    private void buildThemeParam(String theme, Map<String, String> params) {
        if (theme != null) {
            params.put("theme", URLUtilities.encode(theme));
        }
    }

    private String buildPageURL(Weblog weblog, String locale, String pageLink, String category, String dateString, List<String> tags, int pageNum, boolean absolute) {
        StringBuilder pathinfo = new StringBuilder(URL_BUFFER_SIZE);
        buildPreviewPath(weblog, locale, absolute, pathinfo);
        pathinfo.append("page/").append(pageLink);
        Map<String, String> params = new HashMap<>();
        if (dateString != null) {
            params.put("date", dateString);
        }
        if (category != null) {
            params.put("cat", URLUtilities.encode(category));
        }
        if (tags != null && !tags.isEmpty()) {
            params.put("tags", URLUtilities.getEncodedTagsString(tags));
        }
        buildPageParams(pageNum, params);
        buildThemeParam(previewTheme, params);
        return pathinfo.append(URLUtilities.getQueryString(params)).toString();
    }
}