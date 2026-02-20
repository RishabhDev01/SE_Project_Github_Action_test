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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.roller.weblogger.WebloggerException;
import org.apache.roller.weblogger.business.MediaFileManager;
import org.apache.roller.weblogger.business.WebloggerFactory;
import org.apache.roller.weblogger.pojos.MediaFile;
import org.apache.roller.weblogger.pojos.ThemeResource;
import org.apache.roller.weblogger.pojos.Weblog;
import org.apache.roller.weblogger.pojos.WeblogTheme;
import org.apache.roller.weblogger.ui.rendering.util.ModDateHeaderUtil;
import org.apache.roller.weblogger.ui.rendering.util.WeblogResourceRequest;

/**
 * Serves fixed-path files such as old-style uploads and theme resources, which
 * must exist at a fixed-path even if moved in media file folders.
 */
public class ResourceServlet extends HttpServlet {

    private static final long serialVersionUID = 1350679411381917714L;

    private static final Log log = LogFactory.getLog(ResourceServlet.class);

    private ServletContext context = null;

    @Override
    public void init(ServletConfig config) throws ServletException {

        super.init(config);

        log.info("Initializing ResourceServlet");

        this.context = config.getServletContext();
    }

    /**
     * Handles requests for user uploaded resources.
     */
    @Override
    public void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        try {
            WeblogResourceRequest resourceRequest = parseRequest(request);
            Weblog weblog = resourceRequest.getWeblog();

            if (weblog == null) {
                throw new WebloggerException("unable to lookup weblog: "
                        + resourceRequest.getWeblogHandle());
            }

            log.debug("Resource requested [" + resourceRequest.getResourcePath() + "]");

            Resource resource = findResource(weblog, resourceRequest);
            if (resource == null) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            if (ModDateHeaderUtil.respondIfNotModified(request, response, resource.getLastModified(), resourceRequest.getDeviceType())) {
                return;
            } else {
                ModDateHeaderUtil.setLastModifiedHeader(response, resource.getLastModified(), resourceRequest.getDeviceType());
            }

            response.setContentType(this.context.getMimeType(resourceRequest.getResourcePath()));

            try (InputStream resourceStream = resource.getInputStream()) {
                resourceStream.transferTo(response.getOutputStream());
            }

        } catch (Exception e) {
            handleException(request, response, e);
        }
    }

    private WeblogResourceRequest parseRequest(HttpServletRequest request) throws Exception {
        return new WeblogResourceRequest(request);
    }

    private Resource findResource(Weblog weblog, WeblogResourceRequest resourceRequest) {
        try {
            WeblogTheme weblogTheme = weblog.getTheme();
            if (weblogTheme != null) {
                ThemeResource resource = weblogTheme.getResource(resourceRequest.getResourcePath());
                if (resource != null) {
                    return new Resource(resource.getLastModified(), resource.getInputStream());
                }
            }
        } catch (Exception ex) {
            log.debug("Error getting theme resource", ex);
        }

        try {
            MediaFileManager mmgr = WebloggerFactory.getWeblogger().getMediaFileManager();
            MediaFile mf = mmgr.getMediaFileByOriginalPath(weblog, resourceRequest.getResourcePath());
            return new Resource(mf.getLastModified(), mf.getInputStream());
        } catch (Exception ex) {
            log.debug("Unable to get resource", ex);
            return null;
        }
    }

    private void handleException(HttpServletRequest request, HttpServletResponse response, Exception e) throws IOException {
        if (!response.isCommitted()) {
            response.reset();
        }
        log.debug("Error serving resource", e);
        response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
    }

    private static class Resource {
        private long lastModified;
        private InputStream inputStream;

        public Resource(long lastModified, InputStream inputStream) {
            this.lastModified = lastModified;
            this.inputStream = inputStream;
        }

        public long getLastModified() {
            return lastModified;
        }

        public InputStream getInputStream() {
            return inputStream;
        }
    }
}