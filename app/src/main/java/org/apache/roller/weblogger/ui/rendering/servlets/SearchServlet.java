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

package org.apache.roller.weblogger.ui.rendering.servlets;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import javax.servlet.ServletConfig;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.jsp.JspFactory;
import javax.servlet.jsp.PageContext;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.roller.util.RollerConstants;
import org.apache.roller.weblogger.WebloggerException;
import org.apache.roller.weblogger.business.WebloggerFactory;
import org.apache.roller.weblogger.business.themes.ThemeManager;
import org.apache.roller.weblogger.config.WebloggerConfig;
import org.apache.roller.weblogger.config.WebloggerRuntimeConfig;
import org.apache.roller.weblogger.pojos.ThemeTemplate;
import org.apache.roller.weblogger.pojos.Weblog;
import org.apache.roller.weblogger.pojos.WeblogTheme;
import org.apache.roller.weblogger.ui.rendering.Renderer;
import org.apache.roller.weblogger.ui.rendering.RendererManager;
import org.apache.roller.weblogger.ui.rendering.model.ModelLoader;
import org.apache.roller.weblogger.ui.rendering.util.WeblogPageRequest;
import org.apache.roller.weblogger.ui.rendering.util.WeblogSearchRequest;
import org.apache.roller.weblogger.ui.rendering.util.cache.SiteWideCache;
import org.apache.roller.weblogger.ui.rendering.util.cache.WeblogPageCache;
import org.apache.roller.weblogger.util.I18nMessages;
import org.apache.roller.weblogger.util.cache.CachedContent;

/**
 * Handles search queries for weblogs.
 */
public class SearchServlet extends HttpServlet {

    private static final long serialVersionUID = 6246730804167411636L;

    private static final Log log = LogFactory.getLog(SearchServlet.class);

    // Development theme reloading
    private Boolean themeReload;

    /**
     * Init method for this servlet
     */
    @Override
    public void init(ServletConfig servletConfig) throws ServletException {

        super.init(servletConfig);

        log.info("Initializing SearchServlet");

        // Development theme reloading
        themeReload = WebloggerConfig.getBooleanProperty("themes.reload.mode");
    }

    /**
     * Handle GET requests for weblog pages.
     */
    @Override
    public void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        log.debug("Entering");

        try {
            WeblogSearchRequest searchRequest = createSearchRequest(request);
            Weblog weblog = searchRequest.getWeblog();

            if (weblog == null) {
                response.sendError(HttpServletResponse.SC_BAD_REQUEST, "Weblog not found");
                return;
            }

            reloadThemeIfNecessary(weblog);

            WeblogPageRequest pageRequest = createPageRequest(searchRequest);
            Map<String, Object> model = createModel(pageRequest, searchRequest);

            Renderer renderer = getRenderer(weblog, pageRequest);
            CachedContent rendererOutput = renderContent(model, renderer);

            flushResponse(response, rendererOutput);

        } catch (Exception e) {
            log.error("Error handling search request", e);
            response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
        }

        log.debug("Exiting");
    }

    private WeblogSearchRequest createSearchRequest(HttpServletRequest request) {
        try {
            return new WeblogSearchRequest(request);
        } catch (Exception e) {
            log.debug("Error creating search request", e);
            throw new RuntimeException("Invalid search request", e);
        }
    }

    private void reloadThemeIfNecessary(Weblog weblog) {
        if (themeReload && !weblog.getEditorTheme().equals(WeblogTheme.CUSTOM)) {
            try {
                ThemeManager manager = WebloggerFactory.getWeblogger().getThemeManager();
                boolean reloaded = manager.reLoadThemeFromDisk(weblog.getEditorTheme());
                if (reloaded) {
                    if (WebloggerRuntimeConfig.isSiteWideWeblog(weblog.getHandle())) {
                        SiteWideCache.getInstance().clear();
                    } else {
                        WeblogPageCache.getInstance().clear();
                    }
                    I18nMessages.reloadBundle(weblog.getLocaleInstance());
                }
            } catch (Exception ex) {
                log.error("ERROR - reloading theme " + ex);
            }
        }
    }

    private WeblogPageRequest createPageRequest(WeblogSearchRequest searchRequest) {
        WeblogPageRequest pageRequest = new WeblogPageRequest();
        pageRequest.setWeblogHandle(searchRequest.getWeblogHandle());
        pageRequest.setWeblogCategoryName(searchRequest.getWeblogCategoryName());
        pageRequest.setLocale(searchRequest.getLocale());
        pageRequest.setDeviceType(searchRequest.getDeviceType());
        pageRequest.setAuthenticUser(searchRequest.getAuthenticUser());
        return pageRequest;
    }

    private Map<String, Object> createModel(WeblogPageRequest pageRequest, WeblogSearchRequest searchRequest) {
        Map<String, Object> model = new HashMap<>();
        try {
            PageContext pageContext = JspFactory.getDefaultFactory()
                    .getPageContext(this, null, null, "", false, RollerConstants.EIGHT_KB_IN_BYTES, true);

            Map<String, Object> initData = new HashMap<>();
            initData.put("request", null);
            initData.put("pageContext", pageContext);
            initData.put("parsedRequest", pageRequest);
            initData.put("searchRequest", searchRequest);
            initData.put("urlStrategy", WebloggerFactory.getWeblogger().getUrlStrategy());

            String searchModels = WebloggerConfig.getProperty("rendering.searchModels");
            ModelLoader.loadModels(searchModels, model, initData, true);

            if (WebloggerRuntimeConfig.isSiteWideWeblog(pageRequest.getWeblogHandle())) {
                String siteModels = WebloggerConfig.getProperty("rendering.siteModels");
                ModelLoader.loadModels(siteModels, model, initData, true);
            }
        } catch (WebloggerException ex) {
            log.error("Error loading model objects for page", ex);
            throw new RuntimeException("Error loading model objects", ex);
        }
        return model;
    }

    private Renderer getRenderer(Weblog weblog, WeblogPageRequest pageRequest) {
        try {
            ThemeTemplate page = weblog.getTheme().getTemplateByAction(ThemeTemplate.ComponentType.SEARCH);
            if (page == null) {
                page = weblog.getTheme().getDefaultTemplate();
            }
            if (page == null) {
                throw new WebloggerException("Could not lookup default page for weblog " + weblog.getHandle());
            }
            return RendererManager.getRenderer(page, pageRequest.getDeviceType());
        } catch (Exception e) {
            log.error("Couldn't find renderer for rsd template", e);
            throw new RuntimeException("Error getting renderer", e);
        }
    }

    private CachedContent renderContent(Map<String, Object> model, Renderer renderer) {
        CachedContent rendererOutput = new CachedContent(RollerConstants.FOUR_KB_IN_BYTES);
        try {
            renderer.render(model, rendererOutput.getCachedWriter());
            rendererOutput.flush();
            rendererOutput.close();
        } catch (Exception e) {
            log.error("Error during rendering for rsd template", e);
            throw new RuntimeException("Error during rendering", e);
        }
        return rendererOutput;
    }

    private void flushResponse(HttpServletResponse response, CachedContent rendererOutput) {
        try {
            response.setContentType("text/html; charset=utf-8");
            response.setContentLength(rendererOutput.getContent().length);
            response.getOutputStream().write(rendererOutput.getContent());
        } catch (IOException e) {
            log.error("Error flushing response", e);
            throw new RuntimeException("Error flushing response", e);
        }
    }
}