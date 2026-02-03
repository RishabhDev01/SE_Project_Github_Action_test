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
import java.io.InputStream;
import javax.servlet.ServletConfig;
import javax.servlet.ServletContext;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.apache.commons.lang3.StringUtils;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.roller.weblogger.WebloggerException;
import org.apache.roller.weblogger.business.MediaFileManager;
import org.apache.roller.weblogger.business.WebloggerFactory;
import org.apache.roller.weblogger.pojos.MediaFile;
import org.apache.roller.weblogger.pojos.Theme;
import org.apache.roller.weblogger.pojos.ThemeResource;
import org.apache.roller.weblogger.pojos.WeblogTheme;
import org.apache.roller.weblogger.pojos.Weblog;
import org.apache.roller.weblogger.ui.rendering.util.ModDateHeaderUtil;
import org.apache.roller.weblogger.ui.rendering.util.WeblogPreviewResourceRequest;

/**
 * Special previewing servlet which serves files uploaded by users as well as
 * static resources in shared themes. This servlet differs from the normal
 * ResourceServlet because it can accept urls parameters which affect how it
 * behaves which are used for previewing.
 */
public class PreviewResourceServlet extends HttpServlet {

    private static final Log log = LogFactory.getLog(PreviewResourceServlet.class);

    private ServletContext context = null;

    @Override
    public void init(ServletConfig config) throws ServletException {

        super.init(config);

        log.info("Initializing PreviewResourceServlet");

        this.context = config.getServletContext();
    }

    /**
     * Handles requests for user uploaded resources.
     */
    @Override
    public void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        try {
            WeblogPreviewResourceRequest resourceRequest = new WeblogPreviewResourceRequest(request);
            Weblog weblog = resourceRequest.getWeblog();

            if (weblog == null) {
                throw new WebloggerException("unable to lookup weblog: " + resourceRequest.getWeblogHandle());
            }

            log.debug("Resource requested [" + resourceRequest.getResourcePath() + "]");

            ResourceResolver resourceResolver = new ResourceResolver(resourceRequest, weblog, context);
            Resource resource = resourceResolver.resolveResource();

            if (resource == null) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            if (ModDateHeaderUtil.respondIfNotModified(request, response, resource.getLastModified(), resourceRequest.getDeviceType())) {
                return;
            } else {
                ModDateHeaderUtil.setLastModifiedHeader(response, resource.getLastModified(), resourceRequest.getDeviceType());
            }

            response.setContentType(context.getMimeType(resourceRequest.getResourcePath()));

            try (InputStream resourceStream = resource.getInputStream()) {
                resourceStream.transferTo(response.getOutputStream());
            }

        } catch (Exception e) {
            log.error("Error handling request", e);
            response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
        }
    }

    private static class ResourceResolver {

        private final WeblogPreviewResourceRequest resourceRequest;
        private final Weblog weblog;
        private final ServletContext context;

        public ResourceResolver(WeblogPreviewResourceRequest resourceRequest, Weblog weblog, ServletContext context) {
            this.resourceRequest = resourceRequest;
            this.weblog = weblog;
            this.context = context;
        }

        public Resource resolveResource() {
            // first, see if we have a preview theme to operate from
            if (!StringUtils.isEmpty(resourceRequest.getThemeName())) {
                Theme theme = resourceRequest.getTheme();
                ThemeResource resource = theme.getResource(resourceRequest.getResourcePath());
                if (resource != null) {
                    return new ThemeResourceWrapper(resource);
                }
            }

            // second, see if resource comes from weblog's configured shared theme
            try {
                WeblogTheme weblogTheme = weblog.getTheme();
                if (weblogTheme != null) {
                    ThemeResource resource = weblogTheme.getResource(resourceRequest.getResourcePath());
                    if (resource != null) {
                        return new ThemeResourceWrapper(resource);
                    }
                }
            } catch (Exception ex) {
                log.error("Error getting theme resource", ex);
                return null;
            }

            // if not from theme then see if resource is in weblog's upload dir
            try {
                MediaFileManager mmgr = WebloggerFactory.getWeblogger().getMediaFileManager();
                MediaFile mf = mmgr.getMediaFileByOriginalPath(weblog, resourceRequest.getResourcePath());
                return new MediaFileWrapper(mf);
            } catch (Exception ex) {
                log.error("Error getting media file resource", ex);
                return null;
            }
        }
    }

    private static abstract class Resource {
        public abstract long getLastModified();
        public abstract InputStream getInputStream() throws IOException;
    }

    private static class ThemeResourceWrapper extends Resource {
        private final ThemeResource themeResource;

        public ThemeResourceWrapper(ThemeResource themeResource) {
            this.themeResource = themeResource;
        }

        @Override
        public long getLastModified() {
            return themeResource.getLastModified();
        }

        @Override
        public InputStream getInputStream() throws IOException {
            return themeResource.getInputStream();
        }
    }

    private static class MediaFileWrapper extends Resource {
        private final MediaFile mediaFile;

        public MediaFileWrapper(MediaFile mediaFile) {
            this.mediaFile = mediaFile;
        }

        @Override
        public long getLastModified() {
            return mediaFile.getLastModified();
        }

        @Override
        public InputStream getInputStream() throws IOException {
            return mediaFile.getInputStream();
        }
    }
}